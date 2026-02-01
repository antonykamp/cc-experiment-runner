"""State persistence for --continue support."""

from dataclasses import dataclass
from pathlib import Path
from cc_performance_analysis.logger import logger


@dataclass
class SavedState:
    run: int = 0
    iteration: int = 0
    baseline_branch: str = ""
    session_id: str = ""


def _state_file_path(prefix: str, state_dir: Path) -> Path:
    return state_dir / f".state-{prefix}"


def save_state(
    prefix: str,
    run: int,
    iteration: int,
    baseline_branch: str,
    session_id: str,
    state_dir: Path,
) -> None:
    """Save current progress to a state file."""
    path = _state_file_path(prefix, state_dir)
    path.write_text(
        f"RUN={run}\n"
        f"ITERATION={iteration}\n"
        f"BASELINE_BRANCH={baseline_branch}\n"
        f"SESSION_ID={session_id}\n"
    )
    session_info = f", session={session_id}" if session_id else ""
    logger.info(f"State saved: run={run}, iteration={iteration}{session_info}")


def load_state(prefix: str, state_dir: Path) -> SavedState | None:
    """Load state from file. Returns None if no state file exists."""
    path = _state_file_path(prefix, state_dir)
    if not path.exists():
        logger.error(f"No saved state found for prefix '{prefix}'")
        logger.error(f"State file not found: {path}")
        return None

    state = SavedState()
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        match key.strip():
            case "RUN":
                state.run = int(value)
            case "ITERATION":
                state.iteration = int(value)
            case "BASELINE_BRANCH":
                state.baseline_branch = value
            case "SESSION_ID":
                state.session_id = value

    session_info = f", session={state.session_id}" if state.session_id else ""
    logger.info(
        f"Loaded state: run={state.run}, iteration={state.iteration}, "
        f"baseline={state.baseline_branch}{session_info}"
    )
    return state


def clear_state(prefix: str, state_dir: Path) -> None:
    """Remove the state file for a prefix."""
    path = _state_file_path(prefix, state_dir)
    path.unlink(missing_ok=True)
    logger.info(f"State cleared for prefix '{prefix}'")
