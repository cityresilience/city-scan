# Running a Scan

#### Step 1: Configure Setup

City Scan uses multiple programming languages and software to run, including:

- [Git](setup.md#git)
- [Python](setup.md#python)
- [R](setup.md#r)
- [Quarto](setup.md#quarto)
- [Google Cloud](setup.md#gcloud) - for accessing data, see [authentication](../reference/googlecloud.md) details.


See [setup.md](setup.md) for detailed instruction.


#### Step 2: Clone the Repository

```
git clone -b unified https://github.com/varinaldi/city-scan-automation.git
cd city-scan-automation
```

Install the `scan` CLI (one-time):
```
pip install -e .
```
This gives you the `scan` command as a shortcut for `python -m tasks` — both work interchangeably.

Verify your environment is ready:
```
scan --check
```
Runs a preflight on R, Python, GEE, GCS, Quarto, and inputs. Targets a subset with e.g. `scan --check r gee`.


#### Step 3: Configure Inputs

Adjust the files in the `inputs/` folder for your specific project:
- Use `AOI/` folder and store your AOI boundary file there
- Modify `city_inputs.yml` and `menu.yml` with your analysis parameters

#### Step 4: Running Tasks

*Make sure the Python environment is activated*.

Executing tasks can be done from the `city-scan` directory or from within `mnt/scan-id`. General form:
```
scan {TASKNAME} {FLAG}
```

Each task is divided into different steps, defined by `{FLAG}`:
- **`--collect`** runs data collection and saves outputs in `02-process-outputs/spatial` or `/tabular`
- **`--analyze`** runs data analysis and creates output CSVs in `02-process-outputs/tabular`
- **`--all`** runs both **`--collect`** and **`--analyze`**, reads `menu.yml`
- **`--multianalysis`** runs cross-task analysis (currently only for fathom)

To run all tasks set to true in `menu.yml` in parallel (recommended):
```
scan --all 
```
This opens a Terminal UI (TUI) showing per-task progress and logs.

When running the above from
- **`city-scan`** root — initializes `mnt/scan-id` and copies all necessary folders.
- For an existing scan, target it with `--scan-id`:
    ```
    scan --all --parallel --scan-id 2026-02-malta-malta
    ```
- Inside **`mnt/scan-id`** — outputs files into the local `02-process-outputs/`.


To run an individual task or a set of tasks:
```
# Individual task
scan wsf

# Multiple tasks
scan wsf population forest
```

Run specific steps with `{FLAG}`:
```
# Collect step only
scan wsf --collect

# Analyze step only for multiple tasks
scan wsf population green --analyze
```

Other available flags:
```
# Show available tasks
scan --list

# Re-run using the city's existing code (no resync from root)
scan --all -k --scan-id 2026-02-malta-malta
```

#### Step 4b: Multi-analysis

Some tasks have cross-task analysis scripts (e.g. flood exposure calculations that combine flood and WSF data). Run these after all individual tasks have completed:
```
scan --all --multianalysis
```

### Rendering Maps and Charts

#### Step 5: Rendering Maps and Charts

After data collection and analysis, generate maps and charts via the `--render` flag:

```
# Static maps — applies styling from source/layers.yml, writes PNGs to 03-render-output/maps/
scan --render maps --scan-id 2026-02-malta-malta

# Charts for a specific task — writes HTML to tasks/{name}/charts/index.html
scan --render charts elevation --scan-id 2026-02-malta-malta
```

Maps read spatial data from `02-process-output/spatial/`. Charts read CSVs from `02-process-output/tabular/`.

#### Step 6: Scan Calculations Reference Sheet

The `scan-calculations` reads `sections.yml` to determine section order, then assembles all per-task `charts/index.qmd` into a single combined HTML report:

```
scan --render scan-calculations --scan-id 2026-02-malta-malta
```

The compiled report is saved to `scan-calculations/scan-calculations.html`.

If `scan_calculations: True` is set in `menu.yml`, the scan-calculations folder is automatically copied to the city folder when running `scan --all`.

See [scan-calculations/README.md](../../scan-calculations/README.md) for details.
