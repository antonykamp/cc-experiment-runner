"""Configuration constants for the performance analysis."""

import os

ITERATIONS_PER_RUN = 1
TOTAL_RUNS = 3
TIMEOUT_SECONDS = 2 * 60 * 60 # 4 hours
TIMEOUT_WARNING_THRESHOLD = 60  # seconds
ITERATION_TIMEOUT_SECONDS = int(2 * 60 * 60)  # 1.5 hours per iteration
STARTUP_DELAY = 1
TERMINATION_GRACE_PERIOD = 5

PLUGIN_DIR = os.environ.get("CC_PLUGIN_DIR", "")
CLAUDE_FLAGS = "--dangerously-skip-permissions"

BENCHMARK_ORDER = [
    "bounce",
    "list",
    "queens",
    "sieve",
    "towers",
    "methodcall",
]
BENCHMARKS = {
    "bounce": "20 100",
    "list": "20 100",
    "queens": "20 3000",
    "sieve": "20 10000",
    "towers": "20 100",
    "methodcall": "20 100",
}
