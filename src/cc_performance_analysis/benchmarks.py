"""Benchmark runner."""

import subprocess
import time
from pathlib import Path

from cc_performance_analysis.config import (
    BENCHMARK_ORDER,
    BENCHMARKS,
    ITERATIONS_PER_RUN,
)
from cc_performance_analysis.logger import logger


def run_benchmarks(output_file: str, run_num: int, prefix: str) -> bool:
    """Run all benchmarks and save results."""
    logger.info(f"--- Running benchmarks for run {run_num} ---")

    build = subprocess.run(
        ["./mvnw", "package", "-q"], capture_output=True, text=True
    )
    if build.returncode != 0:
        logger.warning(f"Build failed, skipping benchmarks for run {run_num}")
        Path(output_file).write_text("Build failed - benchmarks skipped\n")
        return False

    lines = [
        f"=== Benchmark Results for {prefix}-run-{run_num} ===",
        f"Date: {time.strftime('%c')}",
        f"Final branch: {prefix}-run-{run_num}-iteration-{ITERATIONS_PER_RUN}",
        "",
    ]

    for benchmark in BENCHMARK_ORDER:
        lines.append(f"--- {benchmark} ---")
        params = BENCHMARKS[benchmark]
        result = subprocess.run(
            ["./lox", "harness.lox", benchmark, *params.split()],
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            output += f"\n{benchmark} benchmark failed"
        lines.append(output.strip())
        lines.append("")

    content = "\n".join(lines)
    logger.info(content)
    Path(output_file).write_text(content + "\n")
    logger.info(f"Benchmark results saved to: {output_file}")
    return True
