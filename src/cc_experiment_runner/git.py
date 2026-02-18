"""Git helper functions."""

import subprocess
from cc_experiment_runner.logger import logger


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command."""
    return subprocess.run(
        ["git", *args],
        check=check,
        capture_output=True,
        text=True,
    )


def branch_exists(branch: str) -> bool:
    """Check if a git branch exists."""
    result = run_git("rev-parse", "--verify", branch, check=False)
    return result.returncode == 0


def has_uncommitted_changes() -> bool:
    """Check if the working directory has uncommitted changes."""
    result = run_git("status", "--porcelain")
    return bool(result.stdout.strip())


def commit_if_needed(message: str) -> None:
    """Commit uncommitted changes with a message."""
    if has_uncommitted_changes():
        logger.info(f"Committing changes: {message}")
        run_git("add", "-A")
        run_git("commit", "-m", message, check=False)
