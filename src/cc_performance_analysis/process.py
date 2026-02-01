"""Process management utilities."""

import os
import signal
import subprocess
import time

from cc_performance_analysis.config import TERMINATION_GRACE_PERIOD
from cc_performance_analysis.logger import logger


def terminate_process(pid: int | None, grace_period: int = TERMINATION_GRACE_PERIOD) -> None:
    """Terminate a process and all its children."""
    if pid is None:
        return
    try:
        os.kill(pid, 0)
    except OSError:
        return

    logger.info(f"Terminating process {pid} and children...")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    subprocess.run(["pkill", "-P", str(pid)], capture_output=True)
    time.sleep(grace_period)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    subprocess.run(["pkill", "-9", "-P", str(pid)], capture_output=True)
