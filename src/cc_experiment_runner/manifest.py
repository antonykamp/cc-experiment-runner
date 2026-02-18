"""Structured manifest for benchmark output files."""

import json
from datetime import datetime, timezone
from pathlib import Path

from cc_bench_schema.manifest import MANIFEST_FILENAME


def init_manifest(output_dir: Path, experiment_id: str, baseline_branch: str) -> Path:
    """Create manifest.json with metadata. Returns the manifest path."""
    manifest_path = output_dir / MANIFEST_FILENAME
    manifest = {
        "experiment_id": experiment_id,
        "baseline_branch": baseline_branch,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "runs": {},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest_path


def add_benchmark_files(
    manifest_path: Path, run_id: int, iteration_id: int, benchmark_files: dict[str, str]
) -> None:
    """Append benchmark file entries for one (run, iteration) to the manifest."""
    if not benchmark_files:
        return

    manifest = json.loads(manifest_path.read_text())
    runs = manifest["runs"]
    run_key = str(run_id)
    if run_key not in runs:
        runs[run_key] = {}
    runs[run_key][str(iteration_id)] = benchmark_files
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def finalize_manifest(manifest_path: Path) -> None:
    """Write completed_at timestamp."""
    manifest = json.loads(manifest_path.read_text())
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
