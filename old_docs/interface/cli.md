# CLI Reference

## Prerequisites

1. Activate the conda environment:
   ```bash
   conda activate cityscan
   ```

2. Navigate to the project root:
   ```bash
   cd city-scan-automation
   ```

3. Install the `scan` command (first time only):
   ```bash
   pip install -e .
   ```

All commands below must be run from the `city-scan-automation/` directory with the environment active.

## Data Collection & Analysis

```bash
# Single city (reads from inputs/)
scan --all
scan wsf
scan wsf population forest
scan wsf --collect
scan wsf --analyze

# Existing city
scan --all --scan-id 2026-04-namibia-windhoek
scan elevation --scan-id 2026-04-namibia-windhoek

# Multi-city batch (reads from inputs/multi_inputs.yml)
scan --all --multicity
scan elevation --multicity
scan --all --multicity --parallel
```

## Rendering

Render commands run from root — no need to `cd` into the city folder.

```bash
# Static maps (runs core/R/maps-static.R)
scan --render maps --scan-id 2026-04-namibia-windhoek

# Scan calculations (generates index.qmd + quarto render)
scan --render scan-calculations --scan-id 2026-04-namibia-windhoek

# Single task charts (renders tasks/{task}/charts/index.qmd)
scan elevation --render charts --scan-id 2026-04-namibia-windhoek

# Render for all cities
scan --render maps --multicity
scan --render scan-calculations --multicity
```

## Other Commands

```bash
# List available tasks
scan --list

# Multianalysis (R/Python cross-task analysis)
scan --multianalysis --scan-id 2026-04-namibia-windhoek
scan fathom --multianalysis --scan-id 2026-04-namibia-windhoek
```

## Flags

| Flag | Description |
|---|---|
| `--all` | Run all tasks enabled in menu.yml |
| `--scan-id {id}` | Target an existing city folder in mnt/ |
| `--multicity` | Batch run from inputs/multi_inputs.yml |
| `--collect` | Collection step only |
| `--analyze` | Analysis step only |
| `--visualize` | Visualization step only |
| `--render {target}` | Render: `maps`, `scan-calculations`, or `charts` |
| `--parallel` | Run tasks concurrently with TUI |
| `--upload` | Upload outputs to GCS after each step |
| `--list` | Show available tasks and their steps |

## Note

`python -m tasks` works the same as `scan` without needing `pip install -e .`.
