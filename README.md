# Performance Analysis Script Usage

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed
- Python 3.12+
- `claude` CLI available on PATH

## Installation

```bash
cd cc-performance-analysis
uv sync
```

## Quick Start

```bash
# Via the installed console script
cc-perf-analysis <directory> <prefix> [baseline-branch]

# Or via uv run
uv run cc-perf-analysis <directory> <prefix> [baseline-branch]

# Or as a module
uv run python -m cc_performance_analysis <directory> <prefix> [baseline-branch]
```

**Examples:**

```bash
# Run with plugin enabled (default)
cc-perf-analysis ../byopl24-02 2025-01-30--perf main

# Run without plugin
cc-perf-analysis --no-plugin ../byopl24-02 2025-01-30--perf main
```

## Parameters

### Positional Arguments

- `directory` - Path to the project directory where Claude and git operations run
- `prefix` - Unique identifier for this analysis run (used in branch names)
- `baseline-branch` - (Optional) Git branch to use as baseline (default: `main`)

### Options

- `--continue` - Resume from saved state after interruption or rate limit
- `--remaining-time <seconds>` - Specify remaining timeout when resuming (use with `--continue`)
- `--no-plugin` - Run analysis without the plugin (default: with plugin enabled)

## How It Works

1. **Creates isolated branches** for each iteration: `<prefix>-run-<N>-iteration-<M>`
2. **Runs Claude autonomously** with your prompt for multiple iterations
3. **Each iteration** builds upon the previous one's improvements
4. **Commits changes** automatically with descriptive messages
5. **Runs benchmarks** at the end of each run

## Configuration

Default settings in `src/cc_performance_analysis/config.py`:
- **Iterations per run**: 10
- **Total runs**: 5
- **Timeout per run**: 2 hours

## Handling Rate Limits

When Claude hits the rate limit:

1. **Script automatically saves state** (branch, iteration)
2. **Changes are committed** as "Work in progress"
3. **Script pauses** with instructions

**To resume:**
```bash
cc-perf-analysis --continue <directory> <prefix> 
```

The script will:
- Resume the exact same iteration (no skipping)
- Continue the Claude session with `claude --continue`
- Pick up where it left off

**Alternative - Manual Claude resume:**
```bash
claude --continue 
```

## Example Workflow

```bash
# Start analysis
cc-perf-analysis ../byopl24-02 2025-01-30--opt main

# ... Claude works autonomously ...
# ... Rate limit hit at iteration 3 ...

# Wait for limit to reset, then continue
cc-perf-analysis --continue ../byopl24-02 2025-01-30--opt

# ... Resumes iteration 3 and continues ...
```

## Output

- **Branches**: One per iteration (`<prefix>-run-<N>-iteration-<M>`)
- **Benchmark results**: `benchmark-results-<prefix>-run-<N>.txt`
- **State file**: `.state-<prefix>` (for resuming)

## Error Handling

- **Rate limit**: Saves state and exits (resume with `--continue`)
- **2 consecutive failures**: Assumes persistent issue, saves state and stops
- **Timeout**: Commits partial changes and moves to next run
- **Single error**: Skips iteration and continues

## Project Structure

```
cc-performance-analysis/
├── pyproject.toml
├── README.md
└── src/
    └── cc_performance_analysis/
        ├── __init__.py
        ├── __main__.py        # python -m entry point
        ├── cli.py             # argument parsing and main orchestration
        ├── config.py          # configuration constants
        ├── git.py             # git helper functions
        ├── process.py         # process termination utilities
        ├── state.py           # state persistence for --continue
        ├── claude.py          # Claude CLI invocation and error detection
        └── benchmarks.py      # benchmark runner
```

## Tips

- Use a descriptive prefix with date: `2025-01-30--feature-name`
- Keep prompt files focused on specific optimization goals
- The script creates many branches - clean up old ones periodically
- State files are automatically deleted when runs complete successfully
