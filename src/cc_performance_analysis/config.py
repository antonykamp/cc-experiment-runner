"""Configuration constants for the performance analysis."""

ITERATIONS_PER_RUN = 5
TOTAL_RUNS = 10
TIMEOUT_SECONDS = 2 * 60 * 60  # 2 hours
TIMEOUT_WARNING_THRESHOLD = 60  # seconds
ITERATION_TIMEOUT_SECONDS = 20 * 60  # 20 minutes per iteration
MAX_RECOVERY_ATTEMPTS = 2  # Number of claude --continue retries for stuck iterations
STARTUP_DELAY = 1
TERMINATION_GRACE_PERIOD = 5
CLEANUP_GRACE_PERIOD = 2

PLUGIN_DIR = "../cc-truffle-performance-plugin"
CLAUDE_FLAGS = "--dangerously-skip-permissions"

BENCHMARK_ORDER = ["sieve", "towers", "list", "permute", "queens"]
BENCHMARKS = {
    "sieve": "20 10000",
    "towers": "20 300",
    "list": "20 100",
    "permute": "20 10000",
    "queens": "20 3000",
}
