"""Claude CLI invocation with error detection and timeout management.

Exit codes:
    0   = success
    1   = generic error
    2   = rate limit / API error
    124 = timeout
"""

import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from cc_performance_analysis.config import (
    CLAUDE_FLAGS,
    ITERATIONS_PER_RUN,
    PLUGIN_DIR,
    STARTUP_DELAY,
    TERMINATION_GRACE_PERIOD,
)
from cc_performance_analysis.process import terminate_process
from cc_performance_analysis.logger import logger

_RATE_LIMIT_PATTERN = re.compile(
    r"No messages returned|promise rejected|rate limit|429"
    r"|quota exceeded|too many requests|overloaded_error",
    re.IGNORECASE,
)


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
    with_continue: bool = False,
) -> int:
    """Run Claude with timeout management and error detection.

    Returns:
        exit_code: 0=success, 1=error, 2=rate limit, 124=timeout.
    """
    output_file = tempfile.mktemp(suffix=".txt")

    try:
        if with_continue:
            logger.info(f"Continuing Claude session")
            cmd = ["claude", "--continue", *CLAUDE_FLAGS.split(), "--plugin-dir",
                PLUGIN_DIR,"-p", "Please continue"]
        else:
            cmd = [
                "claude",
                *CLAUDE_FLAGS.split(),
                "--plugin-dir",
                PLUGIN_DIR,
                "-p",
                prompt,
            ]

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
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    outf.write(line)
                    outf.flush()

            reader = threading.Thread(target=stream_output, daemon=True)
            reader.start()

            # Wait for completion with timeout
            wait_start = time.time()
            while proc.poll() is None:
                if time.time() - wait_start >= timeout:
                    logger.info(f"Timeout reached ({timeout}s elapsed)")
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
