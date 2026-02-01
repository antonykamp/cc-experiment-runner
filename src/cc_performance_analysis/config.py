"""Configuration constants for the performance analysis."""

ITERATIONS_PER_RUN = 10
TOTAL_RUNS = 5
TIMEOUT_SECONDS = 2 * 60 * 60  # 2 hours
TIMEOUT_WARNING_THRESHOLD = 60  # seconds
STARTUP_DELAY = 1
TERMINATION_GRACE_PERIOD = 5
CLEANUP_GRACE_PERIOD = 2

PLUGIN_DIR = "../cc-truffle-performance-plugin"
CLAUDE_FLAGS = "--dangerously-skip-permissions"

BENCHMARK_ORDER = ["sieve", "towers", "list", "permute", "queens"]
BENCHMARKS = {
    "sieve": "10 10000",
    "towers": "10 300",
    "list": "10 100",
    "permute": "10 10000",
    "queens": "10 3000",
}
