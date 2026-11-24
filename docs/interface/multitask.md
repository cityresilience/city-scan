# Parallel Task Runner (TUI)

Run all tasks concurrently with a terminal UI:
```
scan --all --parallel
```

## How it works

Tasks are sorted by dependency order (e.g. wsf before fathom, elevation before slope) then submitted to a thread pool. In parallel mode, dependent tasks wait for their prerequisites to finish before starting. Concurrency is further limited by **resource semaphores** — tasks that share the same external service are throttled:

| Resource | Limit | Tasks |
|----------|-------|-------|
| GEE | 1 at a time | forest, landcover, lst, green, ndmi, nightlight |
| GCS | 2 at a time | wsf, fathom, elevation, landcover_burn, basic_info, oxford, coastal_erosion, sea_level_rise |
| OSM | 1 at a time | accessibility, buildings |
| default | 3 at a time | everything else |

## Task dependencies

Some tasks depend on outputs from other tasks. These are handled automatically — both in sequential and parallel mode, the dependency runs first:

| Task | Waits for | Why |
|------|-----------|-----|
| fathom | wsf | Flood exposure analysis needs `wsf_evolution_utm.tif` |
| slope | elevation | Slope is derived from the elevation raster |
| worldpop | ghs_builtup | Urban built area CSV (`_uba.csv`) used for population stats |
| landcover_burn | landcover | Burnability uses land cover classification |

Dependencies are defined in `tasks/__main__.py` (`TASK_DEPENDENCIES`) and `core/py/multitask.py`.

> [!NOTE]
> If a dependency fails, the dependent task will still run but its analyze phase may fail.
> Re-run the dependent task after fixing the prerequisite:
> ```
> python -m tasks fathom --analyze
> ```

## TUI controls

| Key | Action |
|-----|--------|
| ↑↓ | Select task |
| Enter | View task log |
| Esc | Back to task list |
| q | Quit TUI |

The TUI stays open after all tasks complete — press `q` to exit.

## Resource configuration

Edit `core/py/multitask.py` to adjust:
- `RESOURCE_LIMITS` — max concurrent tasks per resource type
- `TASK_RESOURCES` — which resource each task uses

## Known issues

- **R subprocess output**: R tasks (earthquake, cyclones, etc.) have their stdout/stderr captured and routed to the task log. If an R script crashes, the error appears in the task's TUI log.
- **GEE connection pool warnings**: Multiple GEE tasks waiting for the semaphore may show `Connection pool is full` warnings — these are harmless.
- **Oxford/coastal_erosion**: These need R-side GCS auth (`USE_GCS=true` env var). They'll fail silently without it.
