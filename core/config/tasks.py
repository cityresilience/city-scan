"""
Task registry, aliases, dependencies, and auth requirements.
Reads from source/tasks.yml — edit that file to add/modify tasks.
"""
import importlib
import yaml
from pathlib import Path
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

# Load task config from source/tasks.yml
_config_path = Path(__file__).parent.parent.parent / "source" / "tasks.yml"
with open(_config_path) as f:
    _config = yaml.safe_load(f)

GEE_TASKS = set(_config.get("gee_tasks", []))
GCS_TASKS = set(_config.get("gcs_tasks", []))
MENU_KEYS = _config.get("menu_keys", {})
TASK_DEPENDENCIES = {k: set(v) for k, v in _config.get("dependencies", {}).items()}

# Parse aliases from YAML into the format used by discover_tasks
_raw_aliases = _config.get("aliases", {})
ALIASES = {}
for alias, target in _raw_aliases.items():
    if isinstance(target, str):
        ALIASES[alias] = target
    elif isinstance(target, dict):
        folder = target["folder"]
        fns = {k: v for k, v in target.items() if k != "folder"}
        ALIASES[alias] = (folder, fns)


def discover_tasks(tasks_dir=None):
    """Auto-discover tasks from tasks/ folders that have __init__.py.
    tasks_dir defaults to canonical; pass a city folder's tasks/ (after sys.path has
    been rewired to it) to discover that scan's OWN synced tasks instead of canonical's."""
    tasks_dir = Path(tasks_dir) if tasks_dir else Path(__file__).parent.parent.parent / "tasks"
    registry = {}

    for task_dir in sorted(tasks_dir.iterdir()):
        if not task_dir.is_dir() or not (task_dir / "__init__.py").exists():
            continue
        name = task_dir.name
        module_path = f"tasks.{name}"
        try:
            mod = importlib.import_module(module_path)
            has_charts = (task_dir / "charts" / "index.qmd").exists()
            registry[name] = (
                module_path,
                "collect" if hasattr(mod, "collect") else None,
                "analyze" if hasattr(mod, "analyze") else None,
                # "visualize" if hasattr(mod, "visualize") else None,
                None,
                "run" if hasattr(mod, "run") else None,
                "charts" if has_charts else None,
            )
        except Exception as e:
            logger.warning(f"Skipping task '{name}': {e}")

    # Add aliases
    for alias, target in ALIASES.items():
        if isinstance(target, str):
            if target in registry:
                registry[alias] = registry[target]
        elif isinstance(target, tuple):
            folder, fns = target
            if folder in registry:
                base = list(registry[folder])
                for step, fn_name in fns.items():
                    step_map = {"collect": 1, "analyze": 2, "visualize": 3, "run": 4, "charts": 5}
                    if step not in step_map:
                        continue
                    idx = step_map[step]
                    base[idx] = fn_name
                registry[alias] = tuple(base)

    return registry


TASK_REGISTRY = discover_tasks()


def menu_enabled(menu, task_name):
    keys = MENU_KEYS.get(task_name, [task_name])
    return any(menu.get(k) for k in keys)


def topo_sort(names, deps=None):
    """Sort tasks so dependencies come before dependents."""
    if deps is None:
        deps = TASK_DEPENDENCIES
    name_set = set(names)
    sorted_list = []
    visited = set()

    def visit(n):
        if n in visited:
            return
        visited.add(n)
        for dep in deps.get(n, set()):
            if dep in name_set:
                visit(dep)
        sorted_list.append(n)

    for n in names:
        visit(n)
    return sorted_list
