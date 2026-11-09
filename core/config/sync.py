"""Project file syncing — copy core/, tasks/, source/, scan-calculations/ to city folder."""
import sys
import shutil
from core.py.log_module import setup_logger
from .paths import PROJECT_ROOT

logger = setup_logger(__name__)

SKIP_PATTERNS = {"__pycache__", ".quarto", "index_files", "index.html", ".Rproj.user", "node_modules"}


def _ignore(dir, files):
    return [f for f in files if f in SKIP_PATTERNS]


def sync_project_files(city_root, sync_targets=None, sync_tasks=None):
    """
    Copy project code (core/, tasks/, source/, scan-calculations/) to city folder.

    Args:
        city_root: Path to city folder (e.g. mnt/2026-03-namibia-windhoek)
        sync_targets: List of targets to sync (e.g. ["tasks", "source", "core"]).
                      None = first run copies everything, subsequent runs prompt.
        sync_tasks: List of specific task names to sync, or None for all tasks.
    """
    if PROJECT_ROOT.resolve() == city_root.resolve():
        return

    has_existing = (city_root / "source").exists() or (city_root / "core").exists()

    # Determine what to sync
    if sync_targets:
        # Explicit --sync targets — no prompting
        targets = set(sync_targets)
    elif not has_existing:
        # First run — copy everything
        targets = {"tasks", "source", "core", "scan-calculations", "web-version"}
    elif not sys.stdin.isatty():
        # Non-interactive — tasks only
        targets = {"tasks"}
    else:
        print("\n  City folder already has project files.")
        print("  [t] Copy tasks only")
        print("  [o] Override everything (city inputs are not affected)")
        print("  [k] Keep as-is (skip syncing)")
        print("  [a] Abort")
        choice = input("  Choose [t/o/a/k]: ").strip().lower()

        if choice == 'a':
            logger.info("Aborted by user.")
            raise SystemExit("Aborted.")
        if choice == 'k':
            logger.info("Keeping existing project files.")
            return
        targets = {"tasks", "source", "core", "scan-calculations", "web-version"} if choice == 'o' else {"tasks"}

    # Sync non-task folders
    synced = []
    for folder in ["core", "source", "scan-calculations", "web-version"]:
        if folder in targets:
            src = PROJECT_ROOT / folder
            dst = city_root / folder
            if src.exists():
                shutil.copytree(src, dst, ignore=_ignore, dirs_exist_ok=True)
                synced.append(folder)

    # Sync task folders
    if "tasks" in targets:
        if sync_tasks is None:
            src = PROJECT_ROOT / "tasks"
            dst = city_root / "tasks"
            if src.exists():
                shutil.copytree(src, dst, ignore=_ignore, dirs_exist_ok=True)
                synced.append("tasks (all)")
        else:
            tasks_dst = city_root / "tasks"
            tasks_dst.mkdir(exist_ok=True)
            main_src = PROJECT_ROOT / "tasks" / "__main__.py"
            if main_src.exists():
                shutil.copy2(main_src, tasks_dst / "__main__.py")
            for task_name in sync_tasks:
                src = PROJECT_ROOT / "tasks" / task_name
                dst = tasks_dst / task_name
                if src.exists():
                    shutil.copytree(src, dst, ignore=_ignore, dirs_exist_ok=True)
            synced.append(f"tasks ({', '.join(sync_tasks)})")

    if synced:
        logger.info(f"Synced: {', '.join(synced)}")
    else:
        logger.info("No files synced")

    # Logs — create once only
    for folder in ["logs"]:
        src = PROJECT_ROOT / folder
        dst = city_root / folder
        if src.exists() and not dst.exists():
            shutil.copytree(src, dst, ignore=_ignore, dirs_exist_ok=True)

    # .here marker for R's here package
    here_dst = city_root / ".here"
    if not here_dst.exists():
        here_dst.touch()
