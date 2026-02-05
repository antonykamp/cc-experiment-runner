"""Main CLI entry point and orchestration logic."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from cc_performance_analysis.benchmarks import run_benchmarks
from cc_performance_analysis.claude import build_iteration_prompt, clear_claude_memory, run_claude_with_timeout
from cc_performance_analysis.config import (
    CLEANUP_GRACE_PERIOD,
    ITERATION_TIMEOUT_SECONDS,
    ITERATIONS_PER_RUN,
    MAX_RECOVERY_ATTEMPTS,
    TIMEOUT_SECONDS,
    TIMEOUT_WARNING_THRESHOLD,
    TOTAL_RUNS,
)
from cc_performance_analysis.git import branch_exists, commit_if_needed, has_uncommitted_changes, run_git
from cc_performance_analysis.process import terminate_process
from cc_performance_analysis.state import clear_state, load_state, save_state
from cc_performance_analysis.logger import logger

STATE_DIR = Path.cwd().resolve()

start_prompt_plugin_file = Path(__file__).parent.parent.parent / "prompts" / "start-plugin.txt"
start_prompt_no_plugin_file = Path(__file__).parent.parent.parent / "prompts" / "start-no-plugin.txt"
continue_prompt_file = Path(__file__).parent.parent.parent / "prompts" / "continue.txt"

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomous Claude Code Performance Analysis",
    )
    parser.add_argument(
        "--continue",
        dest="continue_mode",
        action="store_true",
        help="Resume from saved state",
    )
    parser.add_argument(
        "--remaining-time",
        type=int,
        default=None,
        help="Remaining timeout in seconds (use with --continue to limit time)",
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


def _handle_continue(prefix: str) -> tuple[int, int, str]:
    """Handle --continue mode. Returns (start_run, start_iteration, baseline_branch)."""
    state = load_state(prefix, STATE_DIR)
    if state is None:
        logger.error(f"Cannot continue: no saved state for prefix '{prefix}'")
        sys.exit(1)

    baseline_branch = state.baseline_branch
    start_run = state.run
    start_iteration = state.iteration

    if start_iteration == 0:
        start_iteration = 1
    if start_iteration > ITERATIONS_PER_RUN:
        start_run += 1
        start_iteration = 1
    if start_run > TOTAL_RUNS:
        logger.info("All runs already completed. Nothing to continue.")
        clear_state(prefix, STATE_DIR)
        sys.exit(0)

    last_branch = f"{prefix}-run-{state.run}-iteration-{state.iteration}"
    if state.iteration > 0 and branch_exists(last_branch):
        logger.info(f"Resuming from branch: {last_branch}")
        run_git("checkout", last_branch)
    else:
        logger.info(f"Resuming from baseline: {baseline_branch}")
        run_git("checkout", baseline_branch)

    logger.info(f"Continuing from run {start_run}, iteration {start_iteration}")
    logger.info("")

    return start_run, start_iteration, baseline_branch


def _validate_fresh_run(baseline_branch: str) -> None:
    """Validate preconditions for a fresh (non-continue) run."""
    if has_uncommitted_changes():
        logger.error("Error: Working directory has uncommitted changes. Please commit or stash them first.")
        sys.exit(1)
    if not branch_exists(baseline_branch):
        logger.error(f"Error: Baseline branch '{baseline_branch}' does not exist")
        sys.exit(1)


def _print_header(prefix: str, baseline_branch: str, continue_mode: bool, start_run: int, start_iteration: int, use_plugin: bool) -> None:
    logger.info("=== Claude Code Autonomous Performance Analysis ===")
    logger.info(f"Directory: {STATE_DIR}")
    logger.info(f"Prefix: {prefix}")
    logger.info(f"Baseline: {baseline_branch}")
    logger.info(f"Plugin: {'enabled' if use_plugin else 'disabled'}")
    logger.info(f"Runs: {TOTAL_RUNS}")
    logger.info(f"Iterations per run: {ITERATIONS_PER_RUN}")
    logger.info(f"Timeout per run: {TIMEOUT_SECONDS // 3600}h")
    if continue_mode:
        logger.info(f"Mode: CONTINUE (from run {start_run}, iteration {start_iteration})")
    logger.info("=" * 50)
    logger.info("")


def _handle_rate_limit(
    prefix: str,
    run: int,
    iteration: int,
    baseline_branch: str,
    directory: str,
) -> None:
    logger.info("")
    logger.error("Rate limit or API error detected.")
    logger.info("Keeping current iteration state for resuming...")
    commit_if_needed(f"Iteration {iteration}: Work in progress (rate limit hit)")
    save_state(prefix, run, iteration, baseline_branch, STATE_DIR)
    logger.info("")
    logger.info(f"Rate limit reached. State saved for resuming iteration {iteration}.")
    logger.info("")
    logger.info("To resume the Claude session directly:")
    logger.info(f"  claude --continue")
    logger.info("")
    logger.info(f"To continue the full script (will resume iteration {iteration}):")
    logger.info(f"  cc-perf-analysis --continue {directory} {prefix}")
    sys.exit(3)


def _handle_consecutive_failures(
    prefix: str,
    run: int,
    iteration: int,
    baseline_branch: str,
    consecutive_failures: int,
    directory: str,
) -> None:
    logger.error("Too many consecutive failures detected.")
    logger.info("Keeping current iteration state for resuming...")
    commit_if_needed(f"Iteration {iteration}: Work in progress (multiple failures)")
    save_state(prefix, run, iteration, baseline_branch, STATE_DIR)
    logger.info("")
    logger.error("=" * 42)
    logger.error(f"ERROR: Too many consecutive failures ({consecutive_failures}).")
    logger.error("This likely indicates a persistent issue (e.g., rate limit, API error).")
    logger.error("Stopping to prevent infinite retry loop.")
    logger.error("=" * 42)
    logger.info("To resume the Claude session directly:")
    logger.info(f"  claude --continue")
    logger.info("")
    logger.info(f"To continue the script later (will resume iteration {iteration}):")
    logger.info(f"  cc-perf-analysis --continue {directory} {prefix}")
    sys.exit(4)


def _handle_single_failure(
    prefix: str,
    run: int,
    iteration: int,
    baseline_branch: str,
    branch_name: str,
) -> None:
    run_git("checkout", "--", ".", check=False)
    subprocess.run(["git", "clean", "-fd"], capture_output=True)

    if iteration > 1:
        prev_branch = f"{prefix}-run-{run}-iteration-{iteration - 1}"
        result = run_git("checkout", prev_branch, check=False)
        if result.returncode != 0:
            run_git("checkout", baseline_branch, check=False)
    else:
        result = run_git("checkout", baseline_branch, check=False)
        if result.returncode != 0:
            run_git("checkout", "main", check=False)

    run_git("branch", "-D", branch_name, check=False)
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
    continue_mode = args.continue_mode
    remaining_time_override = args.remaining_time
    use_plugin = args.use_plugin

    # Change into the project directory so all git/benchmark/Claude commands run there
    os.chdir(project_dir)
    STATE_DIR = project_dir

    start_prompt_file = start_prompt_plugin_file if use_plugin else start_prompt_no_plugin_file
    prompt_file = continue_prompt_file if continue_mode else start_prompt_file
    if not prompt_file.exists():
        logger.error(f"Prompt file '{prompt_file}' not found")
        sys.exit(1)

    prompt = prompt_file.read_text()

    start_run = 1
    start_iteration = 1

    if continue_mode:
        start_run, start_iteration, baseline_branch = _handle_continue(prefix)
    else:
        _validate_fresh_run(baseline_branch)

    _print_header(prefix, baseline_branch, continue_mode, start_run, start_iteration, use_plugin)

    # Setup signal handlers with state context
    current_state = {"run": start_run, "iteration": start_iteration}

    def cleanup(signum, frame):
        logger.info("")
        logger.info("Caught interrupt signal - saving state...")
        commit_if_needed(f"Iteration {current_state['iteration']}: Interrupted")
        save_state(prefix, current_state["run"], current_state["iteration"], baseline_branch, STATE_DIR)
        subprocess.run(["pkill", "-P", str(os.getpid())], capture_output=True)
        logger.info("State saved, cleanup complete")
        sys.exit(130)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    for run in range(start_run, TOTAL_RUNS + 1):
        logger.info("")
        logger.info(f"########## STARTING RUN {run} of {TOTAL_RUNS} ##########")
        logger.info(f"Time: {time.strftime('%c')}")
        logger.info("")

        local_start_iteration = start_iteration if run == start_run else 1

        if local_start_iteration == 1:
            result = run_git("checkout", baseline_branch, check=False)
            if result.returncode != 0:
                logger.error(f"Could not checkout baseline branch {baseline_branch}")
                logger.error(f"Skipping run {run}")
                continue
            run_git("reset", "--hard", baseline_branch)

        if remaining_time_override and run == start_run:
            # User specified remaining time - calculate backwards
            run_start = time.time() - (TIMEOUT_SECONDS - remaining_time_override)
        else:
            # Normal case - start timer now
            run_start = time.time()
        consecutive_failures = 0
        max_consecutive_failures = 2

        for iteration in range(local_start_iteration, ITERATIONS_PER_RUN + 1):
            # Update state for signal handler
            current_state["run"] = run
            current_state["iteration"] = iteration

            branch_name = f"{prefix}-run-{run}-iteration-{iteration}"

            logger.info("")
            logger.info(f"--- Run {run}, Iteration {iteration} ---")
            logger.info(f"Branch: {branch_name}")
            logger.info(f"Started: {time.strftime('%c')}")
            logger.info("")

            if branch_exists(branch_name):
                logger.info(f"Resuming existing branch: {branch_name}")
                run_git("checkout", branch_name)
            else:
                run_git("checkout", "-b", branch_name)

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

                # Use --continue on first script resume OR during recovery
                use_continue = continue_mode or (recovery_attempts > 0)

                # Run Claude with iteration timeout
                if use_continue:
                    if recovery_attempts > 0:
                        logger.info(
                            f"Self-recovery attempt {recovery_attempts}/{MAX_RECOVERY_ATTEMPTS} "
                            f"via 'claude --continue'"
                        )
                    exit_code = run_claude_with_timeout(
                        iteration_prompt,
                        remaining,
                        with_continue=True,
                        iteration_timeout=ITERATION_TIMEOUT_SECONDS,
                        use_plugin=use_plugin
                    )
                    continue_mode = False
                else:
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
                    _handle_rate_limit(
                        prefix, run, iteration, baseline_branch, project_dir
                    )

                elif exit_code == 124:
                    # Timeout detected
                    recovery_attempts += 1

                    if recovery_attempts <= MAX_RECOVERY_ATTEMPTS:
                        logger.warning(
                            f"Iteration {iteration} timed out after "
                            f"{ITERATION_TIMEOUT_SECONDS // 60} minutes"
                        )
                        commit_if_needed(
                            f"Iteration {iteration} (timeout, attempt {recovery_attempts}): "
                            f"Partial changes before recovery"
                        )
                        # Loop continues with use_continue=True
                    else:
                        # Exhausted recovery attempts
                        logger.error(
                            f"Iteration {iteration} failed after {MAX_RECOVERY_ATTEMPTS} "
                            f"recovery attempts. Moving to next iteration."
                        )
                        commit_if_needed(
                            f"Iteration {iteration} (timeout, exhausted retries): "
                            f"Final partial changes"
                        )
                        consecutive_failures += 1
                        break  # Exit recovery loop, move to next iteration

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
                            prefix, run, iteration, baseline_branch,
                            consecutive_failures, project_dir
                        )

                    _handle_single_failure(
                        prefix, run, iteration, baseline_branch, branch_name
                    )
                    break  # Exit recovery loop

            # Log completion
            if iteration_successful:
                logger.info("")
                logger.info(f"Completed iteration {iteration} at {time.strftime('%c')}")
                logger.info(f"Branch {branch_name} is ready")

        logger.info("")
        logger.info(f"########## COMPLETED RUN {run} ##########")
        logger.info("")

        clear_claude_memory(project_dir, prefix, run)

        # Save benchmark results to cc-performance-analysis logs directory
        cc_logs_dir = (Path(__file__).parent.parent.parent / "logs").resolve()
        cc_logs_dir.mkdir(parents=True, exist_ok=True)
        benchmark_output = str(cc_logs_dir / f"benchmark-results-{prefix}-run-{run}.txt")
        run_benchmarks(benchmark_output, run, prefix)
        logger.info("")

    clear_state(prefix, STATE_DIR)
    run_git("checkout", baseline_branch)

    logger.info("")
    logger.info("=== Analysis Complete ===")
    logger.info("Created branches:")
    result = run_git("branch", "--list", f"{prefix}-*")
    logger.info(result.stdout)
    logger.info("To compare results, use:")
    logger.info(f"  git diff {baseline_branch}..{prefix}-run-1-iteration-{ITERATIONS_PER_RUN}")
    logger.info(f"  git log --oneline {prefix}-run-1-iteration-1..{prefix}-run-1-iteration-{ITERATIONS_PER_RUN}")