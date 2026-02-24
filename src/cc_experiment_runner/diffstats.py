"""Git diff statistics collection."""

import csv
from pathlib import Path

from cc_bench_schema.diffstats import DIFFSTATS_COLUMNS
from cc_experiment_runner.git import run_git
from cc_experiment_runner.logger import logger


def compute_diffstats(pre_commit: str) -> dict:
    """Compute added/removed line counts from git diff against pre_commit.

    Classifies files into src/ (src_added/src_removed),
    *.md (md_added/md_removed), and total (total_added/total_removed).
    """
    result = run_git("diff", "--numstat", pre_commit, "HEAD", check=False)
    stats = {
        "src_added": 0, "src_removed": 0,
        "md_added": 0, "md_removed": 0,
        "total_added": 0, "total_removed": 0,
    }

    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added_str, removed_str, filepath = parts

        # Binary files show as "-\t-\t{path}"
        added = int(added_str) if added_str != "-" else 0
        removed = int(removed_str) if removed_str != "-" else 0

        stats["total_added"] += added
        stats["total_removed"] += removed

        if filepath.startswith("src/"):
            stats["src_added"] += added
            stats["src_removed"] += removed

        if filepath.endswith(".md"):
            stats["md_added"] += added
            stats["md_removed"] += removed

    return stats


def write_diffstats_row(
    output_dir: str, prefix: str, run_num: int, iteration: int, stats: dict
) -> None:
    """Append a diffstats row to {prefix}--diffstats.csv."""
    csv_file = Path(output_dir) / f"{prefix}--diffstats.csv"
    file_exists = csv_file.exists()

    with open(csv_file, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(DIFFSTATS_COLUMNS)
        writer.writerow([
            prefix, run_num, iteration,
            stats["src_added"], stats["src_removed"],
            stats["md_added"], stats["md_removed"],
            stats["total_added"], stats["total_removed"],
        ])

    logger.info(f"  Wrote diffstats for run {run_num}, iteration {iteration}")
