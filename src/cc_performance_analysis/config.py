"""Configuration constants for the performance analysis."""

ITERATIONS_PER_RUN = 5
TOTAL_RUNS = 5
TIMEOUT_SECONDS = 2 * 60 * 60  # 2 hours
TIMEOUT_WARNING_THRESHOLD = 60  # seconds
ITERATION_TIMEOUT_SECONDS = 30 * 60  # 30 minutes per iteration
MAX_RECOVERY_ATTEMPTS = 5  # Number of retries for stuck iterations before stopping
STARTUP_DELAY = 1
TERMINATION_GRACE_PERIOD = 5
CLEANUP_GRACE_PERIOD = 2

PLUGIN_DIR = "~/Projects/hpi-ma/cc-truffle-performance-plugin"
CLAUDE_FLAGS = "--dangerously-skip-permissions"

BENCHMARK_ORDER = [
    "bounce",
    "list",
    "permute",
    "queens",
    "sieve",
    "towers",
    "methodcall",
    "mandelbrot",
    "nbody",
    "storage",
]
BENCHMARKS = {
    "bounce": "20 100",
    "list": "20 100",
    "permute": "20 10000",
    "queens": "20 3000",
    "sieve": "20 10000",
    "towers": "20 100",
    "methodcall": "20 100",
    "mandelbrot": "20 500",
    "nbody": "20 1",
    "storage": "20 100",
}
