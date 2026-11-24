# Contributing Guide — Tasks Framework

This document explains how to add new analytical modules to the `tasks` framework and integrate them into the pipeline.

This project follows a **modular, reproducible, and readable** design philosophy.
Each task module represents **one analytical domain** (e.g. air quality, population, hazard, etc.).

---
## Git Branching System

Before you start, let's ensure we are on the same page on the branching system. This is to avoid pushing unstable updates to main. 

### Our Branching Model

```
main          → stable / production-like
  │
  └── new_structure   → This is where our initiative lives
         │
         ├── new_structure_alice
         ├── new_structure_bob
         └── new_structure_charlie
```

No one touches `main` directly.
No one pushes to `new_structure` without review.

---

### What Contributors Do

#### Step 1 — Sync with remote

```bash
git fetch origin
git checkout new_structure
git pull
```

#### Step 2 — Create their personal branch

```bash
git checkout -b new_structure_alice
```

Naming convention:

```
new_structure_<name>
```

---

#### Step 3 — Work normally

When you make updates to your code, commit locally:

```bash
git add .
git commit -m "Implement accessibility data parser"
```

#### Step 4 — Push their branch

```bash
git push -u origin new_structure_alice
```

#### Step 5 — Open a Pull Request

On GitHub / GitLab:

```
FROM: new_structure_alice
TO:   new_structure
```

Daniel will review your code.

---

### Safety Rules 

| Rule                                 | Why                   |
| ------------------------------------ | --------------------- |
| No direct commits to `main`          | Prevent breaking prod |
| No direct commits to `new_structure` | Forces review         |
| Always branch from `new_structure`   | Prevents divergence   |
| Small PRs                            | Easier review         |
| One feature per branch               | No tangled work       |

---

## Task Architecture
The idea is to transfer what previously live in `backend/` folder into their new house: `tasks/` folder. 
Each task module must follow the standard structure:

```
tasks/
└── <module_name>/
    ├── __init__.py
    ├── datacollection.py
    ├── dataanalysis.py
    └── datavisualization.py
```

Example:

```
tasks/air_quality/
```

Reference implementation: `tasks/air_quality` 

### File Responsibilities

| File                   | Responsibility                         |
| ---------------------- | -------------------------------------- |
| `datacollection.py`    | Download / load raw data, either via cloud storage, API, direct download, etc. & clip to AOI |
| `dataanalysis.py`      | Perform numerical/statistical/spatial analysis |
| `datavisualization.py` | Generate maps & plots, not as a final polished product, but as an exploratory data analysis effort. Later, we will polish more in frontend.                  |
| `__init__.py`          | Module registration                    |

---

## Linking a New Module to `__main__.py`

Each datacollection, dataanlysis, and datavisualization functions are orchestrated from each folder's `tasks/{task_name}/__init__.py`. Then, all task modules are orchestrated from `tasks/main.py`.

To integrate a new module:

1. Import the module’s pipeline functions in `__init__.py`
2. Call them in the execution sequence


This three-stage pipeline **must be preserved**:

> **Collection → Analysis → Visualization**

---

## Function Design Rules

### Required Function Signatures

All modules must use these standard arguments:

| Parameter                     | Purpose                   |
| ----------------------------- | ------------------------- |
| `city_name: str`              | City identifier           |
| `output_dir: str`             | Root output directory     |
| `aoi: GeoDataFrame`           | Area of interest          |
| `return_*` flags              | Enable standalone testing |

This ensures consistent orchestration.

---

## Documentation & Style Guide

### Docstrings

Every public function **must** include a NumPy-style docstring:

```python
def compute_stats(...):
    """
   Summary of what this function is about.

    Parameters
    ----------
    what are the inputs to this function
    ...
    Returns
    -------
    what are the outputs of this function
    ...
    """
```

### Logging

Use the shared logger:

```python
from utils.log_module import setup_logger
logger = setup_logger(__name__)
```

Never use `print()` for operational logging.

### Error Handling

* Validate inputs at the start of each function
* Log failures with `logger.error(...)`
* Return `None` on failure instead of crashing the pipeline

### Modularity & Readability

* One responsibility per function
* No hidden side effects
* Avoid hard-coded paths — always use `output_dir`
* Favor explicitness over cleverness

---

## Standalone Testing

Every file should support standalone execution:

```python
if __name__ == "__main__":
    # minimal test example
```

This allows rapid local testing without running the full pipeline.

---

## Folder Naming & Structure

Use **snake_case** for module names:

```
flood_event
ghs_builtup
elevation
```

Follow the standard layout shown in `structure.txt` .

---

## Design Philosophy

This framework is designed for:

* reproducibility
* scientific transparency
* easy extension
* clear audit trails

Every contribution should preserve these goals.

---

