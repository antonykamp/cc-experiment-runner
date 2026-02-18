"""Main CLI entry point and orchestration logic."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from cc_experiment_runner.benchmarks import run_benchmarks
from cc_experiment_runner.claude import build_iteration_prompt, clear_claude_memory, run_claude_with_timeout
from cc_experiment_runner.config import (
    ITERATION_TIMEOUT_SECONDS,
    ITERATIONS_PER_RUN,
    MAX_RECOVERY_ATTEMPTS,
    TIMEOUT_SECONDS,
    TIMEOUT_WARNING_THRESHOLD,
    TOTAL_RUNS,
)
from cc_experiment_runner.git import branch_exists, commit_if_needed, has_uncommitted_changes, run_git
from cc_experiment_runner.logger import logger

STATE_DIR = Path.cwd().resolve()

start_prompt_plugin_file = Path(__file__).parent.parent.parent / "prompts" / "start-plugin.txt"
start_prompt_no_plugin_file = Path(__file__).parent.parent.parent / "prompts" / "start-no-plugin.txt"

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomous Claude Code Performance Analysis",
    )
    parser.add_argument(
        "--no-plugin",
        dest="use_plugin",
        action="store_false",
        default=True,
        help="Run analysis without the plugin (default: with plugin)",
    )
    parser.add_argument(
        "directory",
        help="Path to the project directory where Claude and git operations run",
    )
    parser.add_argument(
        "prefix",
        help="Unique identifier for this analysis run (used in branch names)",
    )
    parser.add_argument(
        "baseline_branch",
        nargs="?",
        default="main",
        help="Git branch to use as baseline (default: main)",
    )
    return parser.parse_args()


def _validate_fresh_run(baseline_branch: str) -> None:
    """Validate preconditions for a fresh (non-continue) run."""
    if has_uncommitted_changes():
        logger.error("Error: Working directory has uncommitted changes. Please commit or stash them first.")
        sys.exit(1)
    if not branch_exists(baseline_branch):
        logger.error(f"Error: Baseline branch '{baseline_branch}' does not exist")
        sys.exit(1)


def _print_header(prefix: str, baseline_branch: str, use_plugin: bool) -> None:
    logger.info("=== Claude Code Autonomous Performance Analysis ===")
    logger.info(f"Directory: {STATE_DIR}")
    logger.info(f"Prefix: {prefix}")
    logger.info(f"Baseline: {baseline_branch}")
    logger.info(f"Plugin: {'enabled' if use_plugin else 'disabled'}")
    logger.info(f"Runs: {TOTAL_RUNS}")
    logger.info(f"Iterations per run: {ITERATIONS_PER_RUN}")
    logger.info(f"Timeout per run: {TIMEOUT_SECONDS // 3600}h")
    logger.info("=" * 50)
    logger.info("")


def _handle_rate_limit(run: int, iteration: int) -> None:
    logger.info("")
    logger.error("Rate limit or API error detected.")
    logger.error(f"Stopping at run {run}, iteration {iteration}.")
    sys.exit(3)


def _handle_consecutive_failures(
    run: int,
    iteration: int,
    consecutive_failures: int,
) -> None:
    logger.info("")
    logger.error("=" * 42)
    logger.error(f"ERROR: Too many consecutive failures ({consecutive_failures}).")
    logger.error("This likely indicates a persistent issue (e.g., rate limit, API error).")
    logger.error(f"Stopping at run {run}, iteration {iteration}.")
    logger.error("=" * 42)
    sys.exit(4)


def _handle_single_failure(
    pre_iteration_commit: str,
    iteration: int,
) -> None:
    run_git("reset", "--hard", pre_iteration_commit, check=False)
    subprocess.run(["git", "clean", "-fd"], capture_output=True)
    logger.warning(f"Iteration {iteration} skipped due to error at {time.strftime('%c')}")
    logger.info("")


def main() -> None:
    global STATE_DIR
    args = _parse_args()

    project_dir = Path(args.directory).resolve()
    if not project_dir.is_dir():
        logger.error(f"Project directory '{project_dir}' does not exist")
        sys.exit(1)

    prefix = args.prefix
    baseline_branch = args.baseline_branch
    use_plugin = args.use_plugin

    # Change into the project directory so all git/benchmark/Claude commands run there
    os.chdir(project_dir)
    STATE_DIR = project_dir

    start_prompt_file = start_prompt_plugin_file if use_plugin else start_prompt_no_plugin_file
    if not start_prompt_file.exists():
        logger.error(f"Prompt file '{start_prompt_file}' not found")
        sys.exit(1)

    prompt = start_prompt_file.read_text()

    _validate_fresh_run(baseline_branch)
    _print_header(prefix, baseline_branch, use_plugin)

    def cleanup(signum, frame):
        logger.info("")
        logger.info("Caught interrupt signal - exiting...")
        subprocess.run(["pkill", "-P", str(os.getpid())], capture_output=True)
        sys.exit(130)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Setup directory for benchmark CSV results
    benchmark_dir = str((Path(__file__).parent.parent.parent / "benchmark-results").resolve())

    for run in range(1, TOTAL_RUNS + 1):
        logger.info("")
        logger.info(f"########## STARTING RUN {run} of {TOTAL_RUNS} ##########")
        logger.info(f"Time: {time.strftime('%c')}")
        logger.info("")

        branch_name = f"{prefix}--run-{run}--iteration-1"
        result = run_git("checkout", baseline_branch, check=False)
        if result.returncode != 0:
            logger.error(f"Could not checkout baseline branch {baseline_branch}")
            logger.error(f"Skipping run {run}")
            continue
        run_git("reset", "--hard", baseline_branch)
        if branch_exists(branch_name):
            run_git("branch", "-D", branch_name, check=False)
        run_git("checkout", "-b", branch_name)

        # Clean build after checking out baseline
        logger.info("Running clean build after baseline checkout...")
        build = subprocess.run(
            ["./mvnw", "clean", "package"], capture_output=True, text=True
        )
        if build.returncode != 0:
            logger.warning("Clean build failed after baseline checkout")
            logger.info(build.stdout)
            logger.info(build.stderr)

        # Run benchmarks before the run (iteration 0 = baseline)
        run_benchmarks(benchmark_dir, prefix, run, iteration=0)
        logger.info("")

        run_start = time.time()
        consecutive_failures = 0
        max_consecutive_failures = 2

        for iteration in range(1, ITERATIONS_PER_RUN + 1):
            logger.info("")
            logger.info(f"--- Run {run}, Iteration {iteration} ---")
            logger.info(f"Started: {time.strftime('%c')}")
            logger.info("")

            elapsed = time.time() - run_start
            remaining = int(TIMEOUT_SECONDS - elapsed)

            if remaining <= TIMEOUT_WARNING_THRESHOLD:
                logger.warning(
                    f"Warning: Less than {TIMEOUT_WARNING_THRESHOLD}s remaining. "
                    "Skipping remaining iterations."
                )
                break

            iteration_prompt = build_iteration_prompt(iteration, prompt, run)

            # Iteration execution with recovery on timeout
            recovery_attempts = 0
            iteration_successful = False

            # Create and checkout iteration branch
            iter_branch = f"{prefix}--run-{run}--iteration-{iteration}"
            if iteration == 1:
                # Already on the correct branch from run start
                logger.info(f"Working on branch {iter_branch}")
            else:
                if branch_exists(iter_branch):
                    run_git("branch", "-D", iter_branch, check=False)
                run_git("checkout", "-b", iter_branch)
                logger.info(f"Created and checked out branch {iter_branch}")

            # Track commit before starting iteration for potential revert
            pre_iteration_commit = run_git("rev-parse", "HEAD").stdout.strip()
            # Track elapsed time before iteration for timeout reset on retry
            pre_iteration_elapsed = time.time() - run_start

            while recovery_attempts <= MAX_RECOVERY_ATTEMPTS and not iteration_successful:
                # Calculate remaining run time
                elapsed = time.time() - run_start
                remaining = int(TIMEOUT_SECONDS - elapsed)

                # Check if we have enough time for this iteration
                if remaining <= TIMEOUT_WARNING_THRESHOLD:
                    logger.warning(
                        f"Warning: Less than {TIMEOUT_WARNING_THRESHOLD}s remaining. "
                        "Skipping remaining iterations."
                    )
                    break  # Exit iteration loop entirely

                # Run Claude with iteration timeout
                if recovery_attempts > 0:
                    logger.info(
                        f"Retry attempt {recovery_attempts}/{MAX_RECOVERY_ATTEMPTS}"
                    )

                exit_code = run_claude_with_timeout(
                    iteration_prompt,
                    remaining,
                    iteration_timeout=ITERATION_TIMEOUT_SECONDS,
                    use_plugin=use_plugin
                )

                # Handle exit codes
                if exit_code == 0:
                    # Success
                    consecutive_failures = 0
                    commit_if_needed(f"Iteration {iteration}: Uncommitted changes cleanup")
                    iteration_successful = True

                elif exit_code == 2:
                    # Rate limit - exit immediately, no retry
                    _handle_rate_limit(run, iteration)

                elif exit_code == 124:
                    # Timeout detected - revert and retry same iteration
                    recovery_attempts += 1

                    if recovery_attempts <= MAX_RECOVERY_ATTEMPTS:
                        logger.warning(
                            f"Iteration {iteration} timed out after "
                            f"{ITERATION_TIMEOUT_SECONDS // 60} minutes "
                            f"(attempt {recovery_attempts}/{MAX_RECOVERY_ATTEMPTS})"
                        )
                        # Revert all changes including any commits made during iteration
                        logger.info(f"Reverting to commit {pre_iteration_commit[:8]} and retrying...")
                        run_git("reset", "--hard", pre_iteration_commit, check=False)
                        subprocess.run(["git", "clean", "-fd"], capture_output=True)
                        # Clear Claude memory before fresh retry
                        clear_claude_memory(project_dir, prefix, run)
                        # Reset run timeout to start of this iteration so retries don't count
                        run_start = time.time() - pre_iteration_elapsed
                    else:
                        # Exhausted recovery attempts - exit
                        logger.error(
                            f"Iteration {iteration} failed after {MAX_RECOVERY_ATTEMPTS} "
                            f"retry attempts. Stopping."
                        )
                        sys.exit(5)

                else:
                    # Other errors
                    consecutive_failures += 1
                    logger.error(f"Error: Claude exited with code {exit_code}")
                    logger.error(
                        f"Consecutive failures: {consecutive_failures} of "
                        f"{max_consecutive_failures}"
                    )

                    if consecutive_failures >= max_consecutive_failures:
                        _handle_consecutive_failures(
                            run, iteration, consecutive_failures
                        )

                    _handle_single_failure(pre_iteration_commit, iteration)
                    break  # Exit recovery loop

            # Log completion and run benchmarks after successful iteration
            if iteration_successful:
                logger.info("")
                logger.info(f"Completed iteration {iteration} at {time.strftime('%c')}")
                logger.info("")
                run_benchmarks(benchmark_dir, prefix, run, iteration=iteration)

        logger.info("")
        logger.info(f"########## COMPLETED RUN {run} ##########")
        logger.info("")

        clear_claude_memory(project_dir, prefix, run)
        logger.info("")

    run_git("checkout", baseline_branch)

    # Clean build after final baseline checkout
    logger.info("Running clean build after baseline checkout...")
    build = subprocess.run(
        ["./mvnw", "clean", "package"], capture_output=True, text=True
    )
    if build.returncode != 0:
        logger.warning("Clean build failed after baseline checkout")
        logger.info(build.stdout)
        logger.info(build.stderr)

    logger.info("")
    logger.info("=== Analysis Complete ===")
    logger.info("Created branches:")
    result = run_git("branch", "--list", f"{prefix}-run-*")
    logger.info(result.stdout)
    logger.info("To compare results, use:")
    logger.info(f"  git diff {baseline_branch}..{prefix}-run-1-iteration-1")