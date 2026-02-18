"""Configuration constants for the performance analysis."""

ITERATIONS_PER_RUN = 5
TOTAL_RUNS = 4
TIMEOUT_SECONDS = 4 * 60 * 60  # 4 hours
TIMEOUT_WARNING_THRESHOLD = 60  # seconds
ITERATION_TIMEOUT_SECONDS = 1 * 60 * 60  # 1 hour per iteration
MAX_RECOVERY_ATTEMPTS = 5  # Number of retries for stuck iterations before stopping
STARTUP_DELAY = 1
TERMINATION_GRACE_PERIOD = 5

PLUGIN_DIR = "~/Projects/hpi-ma/cc-truffle-performance-plugin"
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
