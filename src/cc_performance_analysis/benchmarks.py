"""Benchmark runner."""

import csv
import re
import subprocess
from pathlib import Path

from cc_bench_schema.benchmark import BENCHMARK_COLUMNS
from cc_performance_analysis.config import (
    BENCHMARK_ORDER,
    BENCHMARKS,
)
from cc_performance_analysis.logger import logger


def run_benchmarks(output_dir: str, prefix: str, run_num: int, iteration: int) -> bool:
    """Run all benchmarks and save results as CSV files.

    Args:
        output_dir: path to benchmark-results/ directory
        prefix: experiment ID (e.g. 2026-02-15--a-s4--3)
        run_num: run number (1-4)
        iteration: Claude iteration number (0 = before first, 1-5 = after each)
    """
    logger.info(f"--- Running benchmarks for run {run_num}, iteration {iteration} ---")

    build = subprocess.run(
        ["./mvnw", "package", "-q"], capture_output=True, text=True
    )
    if build.returncode != 0:
        logger.warning(f"Build failed, skipping benchmarks for run {run_num}")
        return False

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for benchmark in BENCHMARK_ORDER:
        logger.info(f"  Running {benchmark}...")
        params = BENCHMARKS[benchmark]
        result = subprocess.run(
            ["./lox", "examples/benchmarks/harness.lox", benchmark, *params.split()],
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            logger.warning(f"  {benchmark} benchmark failed")
            logger.info(output.strip())
            continue

        logger.info(output.strip())

        # Parse runtime values from stdout (e.g. "runtime: 571824us")
        runtimes = re.findall(r"runtime:\s*(\d+)us", output)
        if not runtimes:
            logger.warning(f"  No runtime values found for {benchmark}")
            continue

        csv_file = output_path / f"{prefix}--run-{run_num}--iteration-{iteration}--{benchmark}.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(BENCHMARK_COLUMNS)
            for idx, runtime in enumerate(runtimes, start=1):
                writer.writerow([prefix, run_num, iteration, idx, runtime])

        logger.info(f"  Wrote {csv_file}")

    logger.info(f"--- Benchmarks complete for run {run_num}, iteration {iteration} ---")
    return True
