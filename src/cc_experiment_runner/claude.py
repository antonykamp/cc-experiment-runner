"""Claude CLI invocation with error detection and timeout management.

Exit codes:
    0   = success
    1   = generic error
    2   = rate limit / API error
    124 = timeout
"""

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from cc_experiment_runner.config import (
    CLAUDE_FLAGS,
    ITERATIONS_PER_RUN,
    PLUGIN_DIR,
    STARTUP_DELAY,
    TERMINATION_GRACE_PERIOD,
)

_PLUGIN_DIR_RESOLVED = str(Path(PLUGIN_DIR).expanduser())
from cc_experiment_runner.process import terminate_process
from cc_experiment_runner.logger import logger

_RATE_LIMIT_PATTERN = re.compile(
    r"No messages returned|promise rejected|rate limit exceeded"
    r"|quota exceeded|too many requests|overloaded_error",
    re.IGNORECASE,
)


def clear_claude_memory(project_dir: Path, prefix: str, run: int) -> None:
    """Copy Claude memory into working directory, commit, then delete it."""
    encoded = "-" + str(project_dir.expanduser().resolve()).replace("/", "-").lstrip("-")
    memory_dir = Path.home() / ".claude" / "projects" / encoded / "memory"
    if not memory_dir.exists():
        return

    dest = project_dir / ".claude-memory" / f"{prefix}-run-{run}"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(memory_dir, dest, dirs_exist_ok=True)
    logger.info(f"Saved Claude memory to {dest}")

    subprocess.run(["git", "add", str(dest)], cwd=project_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"Save Claude memory for {prefix} run {run}"],
        cwd=project_dir,
        capture_output=True,
    )

    shutil.rmtree(memory_dir)
    logger.info(f"Cleared Claude memory at {memory_dir}")


def build_iteration_prompt(iteration: int, base_prompt: str, run: int) -> str:
    """Build the iteration-specific prompt sent to Claude."""
    parts = [
        base_prompt,
        "",
        f"This is iteration {iteration} of {ITERATIONS_PER_RUN} in run {run}.",
    ]
    if iteration > 1:
        parts.append("Build upon the improvements from the previous iteration.")
    if iteration == ITERATIONS_PER_RUN:
        parts.append("This is the final iteration of this run.")
    parts.append("")
    parts.append(
        "When done with your changes for this iteration, "
        "commit them with a descriptive message summarizing what you improved."
    )
    return "\n".join(parts)


def run_claude_with_timeout(
    prompt: str,
    timeout: int,
    iteration_timeout: int | None = None,
    use_plugin: bool = True,
) -> int:
    """Run Claude with timeout management and error detection.

    Returns:
        exit_code: 0=success, 1=error, 2=rate limit, 124=timeout.
    """
    output_file = tempfile.mktemp(suffix=".txt")

    try:
        cmd = ["claude", *CLAUDE_FLAGS.split()]
        if use_plugin:
            cmd.extend(["--plugin-dir", _PLUGIN_DIR_RESOLVED])
        cmd.extend(["-p", prompt])

        with open(output_file, "w") as outf:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            claude_pid = proc.pid
            time.sleep(STARTUP_DELAY)

            def stream_output() -> None:
                for line in proc.stdout:
                    logger.info(line.rstrip("\n"))
                    outf.write(line)
                    outf.flush()

            reader = threading.Thread(target=stream_output, daemon=True)
            reader.start()

            # Wait for completion with timeout
            wait_start = time.time()

            # Use the more restrictive timeout
            effective_timeout = timeout
            if iteration_timeout is not None:
                effective_timeout = min(timeout, iteration_timeout)

            while proc.poll() is None:
                if time.time() - wait_start >= effective_timeout:
                    logger.info(f"Timeout reached ({effective_timeout}s elapsed)")
                    terminate_process(claude_pid, TERMINATION_GRACE_PERIOD)
                    reader.join(timeout=5)
                    return 124
                time.sleep(1)

            reader.join(timeout=5)
            exit_code = proc.returncode

        # Check for rate limit / API errors
        output_content = Path(output_file).read_text()

        if _RATE_LIMIT_PATTERN.search(output_content):
            logger.info("")
            logger.info("Detected rate limit or API error in Claude output.")
            return 2

        if exit_code != 0 and len(output_content.splitlines()) < 5:
            logger.info("")
            logger.info(
                f"Warning: Claude exited with error {exit_code} "
                "and minimal output (possible rate limit)."
            )
            if not output_content.strip():
                logger.info("Empty output with non-zero exit, treating as rate limit.")
                return 2
            if re.search(r"error|failed|limit", output_content, re.IGNORECASE):
                logger.info("Error detected in output, treating as rate limit.")
                return 2

        return exit_code

    finally:
        try:
            os.unlink(output_file)
        except OSError:
            pass
