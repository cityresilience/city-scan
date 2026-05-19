# Workflow Graph

ASCII diagram of how `inputs/` flows through `tasks/` into outputs, and how rendering produces maps and the combined report.

```
  city-scan-automation/                      mnt/2026-03-tunisia-tunis/                03-render-output/
 - - - - - - - - - - - -                    - - - - - - - - - - - - - -             - - - - - - - - - - - -
  inputs/             ──────── copy ──────▶   01-user-input/
    city_inputs.yml                             city_inputs.yml
    menu.yml                                    menu.yml
    AOI/                                        AOI/

  tasks/             `scan --all`             02-process-output/
    elevation/        ───── --collect ────▶     spatial/         ──▶ `scan --render maps` ──▶ maps/*.png
    fathom/           ───── --analyze ────▶     tabular/
    worldpop/
    ...               ── --multianalysis ─▶     tabular/
      charts/
        index.qmd ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ─ ─ ─ ─ ─  ┐
                                                                            ▼
        └──────────────────── copy ───────▶  tasks/                      includes      ──▶ plots/*.png
  core/                                      core/                          :
  source/                                    source/                        :
  scan-calculations/                         scan-calculations/    ──▶ `scan --render scan-calculations` ──▶ scan-calculations.html
  .here (R Path Resolution)
```

For a sequenced view of which tasks run when (orchestration order, dependencies, parallel groups), see [orchestration-graph.md](orchestration-graph.md).
