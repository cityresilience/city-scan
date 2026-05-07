# Scan Calculations

The scan-calculations reference sheet is a single HTML document that combines all per-task charts into one report. It is generated using Quarto.

## How it works

1. `generate-index.R` runs as a pre-render step (configured in `_quarto.yml`)
2. It reads `sections.yml` to determine the section order
3. For each section, it checks if `tasks/{name}/charts/index.qmd` exists
4. It generates `index.qmd` with Quarto `{{< include >}}` directives for each task
5. Quarto renders `index.qmd` into a self-contained HTML file

## Prerequisites

- All task data must already be collected and analyzed (`python -m tasks --all`)
- Multianalysis must be run for tasks that require it (e.g. `python -m tasks fathom --multianalysis`)
- R packages loaded by `core/R/setup.R` must be installed
- Quarto must be installed

## Usage

Run from inside the city folder (`mnt/scan-id`):

```
quarto render scan-calculations
```

The output is `scan-calculations/scan-calculations.html`.

## Files

```
scan-calculations/
├── _quarto.yml         # Quarto project config (pre-render, theme, format)
├── generate-index.R    # Pre-render script that assembles task qmds
├── sections.yml        # Section order — maps task names to charts/index.qmd
└── index.qmd           # Auto-generated, do not edit manually
```

## Adding a new section

1. Create `tasks/{name}/charts/index.qmd` with your charts
2. Add the task name to `sections.yml` in the desired position

## sections.yml

Controls the order of sections in the report. Each entry maps to `tasks/{name}/charts/index.qmd`:

```yaml
sections:
  - basic_info
  - worldpop
  - oxford
  - wsf
  - landcover
  - elevation
  - slope
  - fathom
  - flood_events
  - earthquake
  - cyclones
  - solar
  - fwi
```

Tasks not listed here will not appear in the report even if they have `charts/index.qmd`.

## Conditional sections

- `oxford` is skipped if the city is not in the Oxford Economics database (checked via `basic_info.yml`)
- Tasks without a `charts/index.qmd` are skipped automatically
