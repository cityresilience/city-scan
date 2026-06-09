# Orchestration Dependency Graph


## Dependencies used by the orchestration layer

```
requirements.txt (orchestration-critical subset)
├── PyYAML==6.0.1              ← reads city_inputs.yml, menu.yml,
│                                tasks.yml, multi_inputs.yml, layers.yml
├── geopandas==1.0.1           ← AOI loading + multipolygon handling
│                                (Scan.aoi, run_multicity, find_country)
├── earthengine-api>=1.6.12    ← core/config/auth.py::init_gee()
├── google-cloud-storage       ← core/config/auth.py::init_gcs(),
│     ==2.16.0                   core/py/gcs_module.py (upload)
├── rasterio==1.3.8            ← raster I/O for collection/analysis
├── shapely==2.0.4             ← AOI geometry ops
└── fiona==1.10.1              ← shp/gpkg read
```

Standard-library orchestration modules: `argparse`-style parsing (custom in
`core/config/cli.py`), `importlib` (task discovery), `subprocess` (R/Quarto),
`threading` / `concurrent.futures` (parallel mode), `termios` / `tty` /
`select` (TUI keybinds), `logging`, `pathlib`, `shutil`.

## Flag targets (from `core/config/cli.py`)

```
--sync     ∈ { tasks, source, core, scan-calculations }   (SYNC_TARGETS)
             • no target  → all four
             • -t         → shortcut for `--sync tasks`
--render   ∈ { maps, scan-calculations, charts }          (render_targets)
             • maps                → Rscript core/R/maps-static.R
             • scan-calculations   → quarto render scan-calculations/
             • charts <task>       → quarto render tasks/<task>/charts/index.qmd
--scan-id  <id>      target existing city folder in mnt/
--all                run every task enabled in menu.yml
--multicity          batch from inputs/multi_inputs.yml
--collect / --analyze / --multianalysis   single-phase run
--parallel           multitask.py TUI runner
--upload             gcs_module.upload_task_outputs()
-e                   use existing city folder (skip folder prompt)
-k / --keep          run with code already in city folder (skip sync)
-t                   shortcut for `--sync tasks`
--list     ∈ { tasks, cities, flags }
```

## Orchestration graph

```
                                USER CLI
                                python -m tasks ...
                        (or `scan ...` via pyproject entry point)
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  tasks/__main__.py                                                                   │
│    main()  — dispatches based on flags                                               │
└──────────────────────────────────────────────────────────────────────────────────────┘
        │            │            │                    │                          │
        ▼            ▼            ▼                    ▼                          ▼
    [--help]    [--list X]  [validate+parse]        [normal]                   [MULTI]
                                │                      │                          │
                                ▼                      │                          ▼
┌───────────────────────────────────────────┐          │    ┌──────────────────────────────────────────────┐
│  core/config/cli.py                       │          │    │ core/py/run.py                               │
│    KNOWN_FLAGS, SYNC_TARGETS (const)      │          │    │   run_multicity(path, args, flags)           │
│    validate_args(args) → err|None         │          │    │     ├─ reads inputs/multi_inputs.yml         │
│    parse_args(args)    → flags dict       │          │    │     ├─ gpd.read_file  (multipolygon mode)    │
│      flags: sync_targets, keep_as_is,     │          │    │     ├─ find_country()                        │
│        use_existing, upload_enabled,      │          │    │     ├─ scan_init()                           │
│        parallel_mode, auto_exit, run_all, │          │    │     ├─ prepare_inputs()                      │
│        multicity, step, scan_id,          │          │    │     └─ subprocess: `scan --scan-id <id> ...` │
│        render_targets, task_names         │          │    │         (loops per city, falls back into     │
└───────────────────────────────────────────┘          │    │          the [normal] path)                  │
                                │                      │    └──────────────────────────────────────────────┘
                                │                      │                          │
                                └──────────────────────┼──────────────────────────┘
                                                       ▼
┌────────────────────────────────────────────────────────────────────┐
│  core/config/scan.py                                               │
│    scan_init(country, city, use_existing) → scan_id                │
│      (prompts [e]xisting / [n]ew unless use_existing or non-tty)   │
│                                                                    │
│    class Scan:                                                     │
│      __init__(scan_id, sync_tasks, skip_sync,                      │
│               use_existing, sync_targets)                          │
│        ├─→ prepare_inputs()      (core/config/inputs.py)           │
│        ├─→ find_country()        (core/py/aoi_module.py)           │
│        ├─→ scan_init()           (self)                            │
│        ├─→ sync_project_files()  (core/config/sync.py)  [skippable]│
│        └─ attrs: city_dir, input_dir, output_dir, render_dir,      │
│           spatial_dir, tabular_dir, menu, sources, font_dict       │
└────────────────────────────────────────────────────────────────────┘
                                                      │
                 ┌────────────────────────────────────┼────────────────────────────────────┐
                 ▼                                    ▼                                    ▼
┌─────────────────────────────────┐ ┌─────────────────────────────────┐ ┌───────────────────────────────────────┐
│ core/config/paths.py            │ │ core/config/inputs.py           │ │ core/config/sync.py                   │
│   PROJECT_ROOT                  │ │   prepare_inputs(               │ │   SKIP_PATTERNS                       │
│   INPUTS  (auto-detect:         │ │     dest, city_inputs,          │ │   _ignore(dir, files)                 │
│     inputs/  OR  01-user-input/)│ │     source_dir,                 │ │   sync_project_files(                 │
│   OUTPUTS (mnt/  OR  city       │ │     aoi_dir, wards_dir,         │ │     city_root,                        │
│            parent)              │ │     override)                   │ │     sync_targets,                     │
│                                 │ │                                 │ │     sync_tasks)                       │
│ core/config/utils.py            │ │   writes city_inputs.yml,       │ │                                       │
│   slugify(name)                 │ │   copies AOI/menu/wards into    │ │   sync_targets ∈ {                    │
│                                 │ │   01-user-input/                │ │     tasks, source, core,              │
│                                 │ │                                 │ │     scan-calculations                 │
│                                 │ │                                 │ │   }   (from cli.py SYNC_TARGETS)      │
│                                 │ │                                 │ │                                       │
│                                 │ │                                 │ │   sync_tasks = list of task folders   │
│                                 │ │                                 │ │                 or None (all tasks)   │
│                                 │ │                                 │ │                                       │
│                                 │ │                                 │ │   modes:                              │
│                                 │ │                                 │ │     sync_targets set  → explicit      │
│                                 │ │                                 │ │     first run         → all 4 targets │
│                                 │ │                                 │ │     non-tty           → tasks only    │
│                                 │ │                                 │ │     else → prompt [t/o/k/a]:          │
│                                 │ │                                 │ │       [t] tasks only                  │
│                                 │ │                                 │ │       [o] override all                │
│                                 │ │                                 │ │       [k] keep as-is                  │
│                                 │ │                                 │ │       [a] abort                       │
└─────────────────────────────────┘ └─────────────────────────────────┘ └───────────────────────────────────────┘

                                                      │
                                  (back in __main__.py after Scan init)
                                                      ▼
        ┌──────────────────┬───────────────────┬───────────────────┬───────────────────┐
        ▼                  ▼                   ▼                   ▼                   ▼
 [--sync targets]   [--upload only]     [--render targets]   [--all / tasks]       [default]

 returns after       backfill upload     calls Rscript        resolves task list   run collect+analyze
 sync_project_       of whole city       / quarto per         from menu.yml +      serially per task
 files() ran in      output dir via      target (see Flag     args via             (uses TASK_REGISTRY,
 Scan init           gcs_module          targets block)       TASK_REGISTRY +      gates by auth)
                                                              topo_sort()
                                                      │                   │                   │
                                                      │                   └─────────┬─────────┘
                                                      │                             ▼
                                                      │       ┌────────────────────────────────────────────┐
                                                      │       │ core/config/tasks.py                       │
                                                      │       │   TASK_REGISTRY     ALIASES                │
                                                      │       │   GEE_TASKS         GCS_TASKS              │
                                                      │       │   MENU_KEYS         TASK_DEPENDENCIES      │
                                                      │       │   discover_tasks()                         │
                                                      │       │   menu_enabled(menu, name)                 │
                                                      │       │   topo_sort(names, deps)                   │
                                                      │       │   ← source/tasks.yml                       │
                                                      │       └────────────────────────────────────────────┘
                                                      │                             │
                                                      │                             ▼
                                                      │       ┌────────────────────────────────────────────┐
                                                      │       │ core/config/auth.py                        │
                                                      │       │   init_gee()     init_gcs()                │
                                                      │       └────────────────────────────────────────────┘
                                                      │                             │
                                                      │                 ┌───────────┴──────────┐
                                                      ▼                 ▼                      ▼
                        ┌────────────────────────────────────────┐   [serial]              [parallel]
                        │ subprocess:                            │      │                      │
                        │   Rscript   core/R/maps-static.R       │      ▼                      ▼
                        │   quarto    render scan-calculations/  │   ┌──────────────┐   ┌──────────────────────────────────────────┐
                        │   quarto    render tasks/<t>/charts/   │   │ run_task(    │   │ core/py/multitask.py                     │
                        └────────────────────────────────────────┘   │   name,      │   │   run_parallel(task_names, scan, step,   │
                                                      │              │   scan,      │   │                 run_task_fn, skip_tasks, │
                                                      ▼              │   step)      │   │                 auto_exit)               │
                        ┌────────────────────────────────────────┐   └──────────────┘   │     ├ TaskState                          │
                        │ core/py/gcs_module.py                  │          │           │     ├ TaskLogHandler                     │
                        │   get_all_files(dir)                   │          │           │     ├ worker()  per task thread          │
                        │   upload_task_outputs(scan, task,      │          │           │     ├ Semaphores  (gee / gcs / osm)      │
                        │                       step,            │          │           │     ├ TUI loop  (termios/tty/select)     │
                        │                       files_before)    │          │           │     └ collect_results                    │
                        └────────────────────────────────────────┘          │           └──────────────────────────────────────────┘
                                                                            │                        │
                                                                            ▼                        │
                                               ┌────────────────────────────────────────────┐        │
                                               │ core/py/run.py                             │◀───────┘
                                               │   run_task(name, scan, step)               │
                                               │     ├ importlib.import_module              │
                                               │     ├ ErrorTracker() context mgr           │
                                               │     └ dispatches to task module:           │
                                               │         collect / analyze / multianalysis  │
                                               └────────────────────────────────────────────┘
                                                                  │
                                                                  ▼
                                               ┌────────────────────────────────────────────┐
                                               │ tasks/{name}/                              │
                                               │   __init__.py  →  collection.py            │
                                               │                   analysis.py              │
                                               │                   multianalysis.R          │
                                               │                   charts/index.qmd         │
                                               └────────────────────────────────────────────┘

                                  BACK IN __main__.py (after runs)
                                                  │
                                                  ▼
                        ┌────────────────────────────────────────────────────────┐
                        │  summary table → logger                                │
                        │  logs/task_report.txt                                  │
                        │    (task | step | status | source | msg | timestamp)   │
                        └────────────────────────────────────────────────────────┘
```

## Utilities (used throughout)

```
core/py/log_module.py    setup_logger(name), set_log_dir(path),
                         _file_handler (module-level)
core/py/error_tracker.py ErrorTracker()  — context manager, captures
                         status + messages per phase
core/py/aoi_module.py    find_country(aoi) → (iso3, name, iso3_list)
core/py/gcs_module.py    get_all_files(dir), upload_task_outputs(
                          scan, task_name, step, files_before)
core/config/gdal_auth.py GDAL cloud config for /vsicurl/ reads
```

Legend: boxes = files, indented lines = functions/attrs within that file.
Arrows = import/call direction.
