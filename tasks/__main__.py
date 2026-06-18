"""City Scan Automation — see docs/orchestration.md for usage."""
import sys
import os

# Add city root (parent of tasks/) to sys.path so core.py imports work from anywhere
_city_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _city_root not in sys.path:
    sys.path.insert(0, _city_root)

from core.py.log_module import setup_logger
from core.config.tasks import (
    TASK_REGISTRY, ALIASES, GEE_TASKS, GCS_TASKS,
    menu_enabled, topo_sort
)
from core.config.cli import parse_args, validate_args, KNOWN_FLAGS
from core.config.run import run_task, run_multicity

logger = setup_logger("tasks")


def main():
    args = sys.argv[1:]

    # =========================================================
    # HELP
    # =========================================================
    if not args or "--help" in args:
        print(__doc__)
        return

    # =========================================================
    # CHECK (environment preflight — runs before scan logic)
    # =========================================================
    if "--check" in args:
        from core.config.cli import CHECK_TARGETS
        from core.config.check_env import run_checks
        idx = args.index("--check")
        targets = []
        for a in args[idx + 1:]:
            if a.startswith("-"):
                break
            if a in CHECK_TARGETS:
                targets.append(a)
            else:
                break
        if not targets:
            targets = sorted(CHECK_TARGETS)
        sys.exit(0 if run_checks(targets) else 1)

    # =========================================================
    # LIST
    # =========================================================
    if "--list" in args:
        idx = args.index("--list")
        list_what = args[idx + 1] if idx + 1 < len(args) else "tasks"

        if list_what == "tasks":
            print(f"\n  {'Task':<20} {'Steps'}")
            print(f"  {'-'*45}")
            for name, entry in sorted(TASK_REGISTRY.items()):
                _, collect_fn, analyze_fn, vis_fn, run_fn, charts_fn = entry
                steps = []
                if collect_fn: steps.append("collect")
                if analyze_fn: steps.append("analyze")
                if charts_fn: steps.append("charts")
                print(f"  {name:<20} {', '.join(steps)}")

        elif list_what == "cities":
            from core.config.paths import OUTPUTS
            print(f"\n  Cities in mnt/:")
            print(f"  {'-'*50}")
            cities = sorted([d.name for d in OUTPUTS.iterdir() if d.is_dir() and (d / "01-user-input").exists()])
            if cities:
                for c in cities:
                    print(f"  {c}")
            else:
                print("  No city folders found.")

        elif list_what == "flags":
            print(f"\n  Available flags:")
            print(f"  {'-'*60}")
            flag_list = [
                ("--all",                "Run all tasks enabled in menu.yml"),
                ("--scan-id {id}",       "Target existing city folder in mnt/"),
                ("--multicity",        "Batch run from inputs/multi_inputs.yml"),
                ("--collect",            "Collection step only"),
                ("--analyze",            "Analysis step only"),
                ("--multianalysis",      "Cross-task analysis (R/Python)"),
                ("--render maps",        "Run maps-static.R"),
                ("--render scan-calculations", "Quarto render scan-calculations"),
                ("--render charts",      "Render task charts (requires task name)"),
                ("--parallel",           "Run tasks concurrently with TUI"),
                ("--upload",             "Upload to GCS: with task=new outputs; with --render=new renders; alone=backfill all"),
                ("--gcs",                "Connect to a scan stored in GCS (requires --scan-id)"),
                ("--download=01,02",     "Pull GCS folders to local (symmetric to --upload)"),
                ("-e",                   "Use existing city folder (skip folder prompt)"),
                ("-t",                   "Shortcut for --sync tasks"),
                ("-k / --keep",          "Run with code already in city folder (no sync)"),
                ("--sync",               "Sync all project files (tasks, source, core, scan-calculations)"),
                ("--sync tasks",         "Sync tasks/ only"),
                ("--sync source",        "Sync source/ only"),
                ("--sync core",          "Sync core/ only"),
                ("--list tasks",         "Show available tasks"),
                ("--list cities",        "Show city folders in mnt/"),
                ("--list flags",         "Show this list"),
                ("--check",              "Preflight environment (all)"),
                ("--check {targets}",    "Preflight subset: r, python, gee, gcs, quarto, inputs"),
            ]
            for flag, desc in flag_list:
                print(f"  {flag:<30} {desc}")

        else:
            print(f"  Unknown list type: '{list_what}'. Use: tasks, cities, or flags")

        print()
        return

    # =========================================================
    # VALIDATE & PARSE
    # =========================================================
    err = validate_args(args)
    if err:
        logger.error(err)
        return

    flags = parse_args(args)

    # =========================================================
    # MULTICITIES
    # =========================================================
    if "--multicity" in args:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        multicity_path = os.path.join(project_root, "inputs", "multi_inputs.yml")
        if not os.path.exists(multicity_path):
            logger.error(f"Multi-city config not found: {multicity_path}")
            return
        run_multicity(multicity_path, args, flags)
        return

    # =========================================================
    # INITIALIZE
    # =========================================================
    from core.config.scan import Scan
    from core.config.paths import INPUTS, OUTPUTS

    scan_id = flags['scan_id']
    step = flags['step']

    header = scan_id.split('-', 2)[-1].replace('-', ' ').title() if scan_id and scan_id.count('-') >= 2 else "City Scan Automation"
    print(f"\n  {header}")
    print(f"  {'─'*40}")

    # =========================================================
    # GCS CONNECT (--gcs): bootstrap a GCS-hosted scan locally
    # =========================================================
    if flags['gcs']:
        from core.py.gcs_module import download_scan_folder
        # --render reads 02 (process-output); stream it from GCS unless downloaded
        streaming = bool(flags['render_targets']) and "02" not in flags['download']
        # 01 is always local. Explicit --download=01 forces overwrite; when
        # streaming a render, keep existing 01 silently (no overwrite prompt).
        ov01 = True if "01" in flags['download'] else (False if streaming else None)
        download_scan_folder(scan_id, "01", overwrite=ov01)
        # Explicit pulls (--download=02,03)
        for folder in flags['download']:
            if folder == "01":
                continue
            download_scan_folder(scan_id, folder, overwrite=True)
        if streaming:
            os.environ['USE_GCS'] = 'true'
            print("  STREAMING DATA FROM GCS")
        elif flags['run_all'] or flags['step']:
            print("  connecting to scan in GCS bucket")

    # Validate --scan-id if provided
    if INPUTS.name == "inputs" and scan_id:
        if not (OUTPUTS / scan_id).exists():
            print(f"  City folder not found: {scan_id}")
            return

    # Determine if running specific tasks (for selective sync)
    _specific_tasks = [a for a in args if not a.startswith("-") and a != scan_id]
    # Resolve aliases to actual folder names for sync (e.g. population → worldpop)
    _resolved = []
    for t in _specific_tasks:
        alias = ALIASES.get(t)
        if isinstance(alias, str):
            _resolved.append(alias)
        elif isinstance(alias, tuple):
            _resolved.append(alias[0])
        else:
            _resolved.append(t)
    # --gcs bootstrap: copy the whole project (core/source/tasks/scan-calculations)
    # into mnt without prompting — but ONLY the first time (when it's not there yet)
    gcs_needs_sync = bool(flags['gcs'] and scan_id and not (
        (OUTPUTS / scan_id / "source").exists() and (OUTPUTS / scan_id / "tasks").exists()))

    sync_tasks = None if flags['run_all'] or gcs_needs_sync or not scan_id else (_resolved or None)
    _sync_targets = (["tasks", "source", "core", "scan-calculations"]
                     if gcs_needs_sync else (flags['sync_targets'] or None))

    scan = Scan(scan_id=scan_id, sync_tasks=sync_tasks,
                skip_sync=((bool(flags['render_targets']) or flags['keep_as_is']) and not flags['sync_targets']) and not gcs_needs_sync,
                use_existing=flags['use_existing'],
                sync_targets=_sync_targets)

    # Set up file logging in city folder
    city_dir = os.path.dirname(str(scan.input_dir))
    from core.py.log_module import set_log_dir
    set_log_dir(os.path.join(city_dir, "logs"))

    # =========================================================
    # SYNC ONLY
    # =========================================================
    if flags['sync_targets'] and not flags['step'] and not flags['run_all'] and not flags['render_targets']:
        task_names_check = [a for a in args if not a.startswith("-") and a != scan_id and a not in flags['sync_targets']]
        if not task_names_check:
            print(f"\n  Synced {', '.join(flags['sync_targets'])} to {scan.cityscan_id}\n")
            return

    # =========================================================
    # UPLOAD ONLY (backfill: --upload with no tasks, no render, no --all)
    # =========================================================
    if flags['upload_enabled'] and not flags['render_targets'] and not flags['run_all']:
        positional = [a for a in args if not a.startswith("-") and a != scan_id]
        if not positional:
            from core.py.gcs_module import upload_inputs, upload_task_outputs
            logger.info(f"Backfill upload: pushing all existing files for {scan.cityscan_id}")
            upload_inputs(scan)
            upload_task_outputs(scan, task_name="backfill", files_before=None)
            return

    # =========================================================
    # RENDER
    # =========================================================
    if flags['render_targets']:
        import subprocess

        # Confirm before rendering (skip if --scan-id given, non-interactive, or multicity)
        render_desc = ', '.join(flags['render_targets'])
        if scan_id or flags['auto_exit'] or INPUTS.name != "inputs" or not sys.stdin.isatty():
            logger.info(f"Rendering {render_desc} for {scan.cityscan_id}")
        else:
            print(f"\n  Render {render_desc} for {scan.cityscan_id}? (y/n)")
            if input("  ").strip().lower() != 'y':
                print("  Aborted.")
                return

        task_names = [a for a in args if not a.startswith("-") and a != scan_id and a not in flags['render_targets']]

        files_before = None
        if flags['upload_enabled']:
            from core.py.gcs_module import get_all_files, upload_task_outputs
            files_before = get_all_files(scan.output_dir) | get_all_files(scan.render_dir)

        for render_target in flags['render_targets']:
            if render_target == "maps":
                if task_names:
                    # Task-specific map rendering
                    tasks_str = "c(" + ",".join(f"'{t}'" for t in task_names) + ")"
                    r_cmd = f"render_tasks <- {tasks_str}; source(here::here('core/R/maps-static.R'))"
                    logger.info(f"Rendering maps for: {', '.join(task_names)}")
                else:
                    r_cmd = "source(here::here('core/R/maps-static.R'))"
                    logger.info("Rendering all static maps...")
                subprocess.run(
                    ["Rscript", "-e", r_cmd],
                    cwd=city_dir, check=True
                )
            elif render_target == "scan-calculations":
                logger.info("Rendering scan-calculations...")
                # pre-render in _quarto.yml runs generate-index.R automatically
                subprocess.run(
                    ["quarto", "render", "scan-calculations/"],
                    cwd=city_dir, check=True
                )
            elif render_target == "charts":
                if not task_names:
                    logger.error("--render charts requires a task name, e.g.: scan elevation --render charts")
                    continue
                for task in task_names:
                    qmd = os.path.join(city_dir, "tasks", task, "charts", "index.qmd")
                    if os.path.exists(qmd):
                        logger.info(f"Rendering {task} charts...")
                        subprocess.run(
                            ["quarto", "render", qmd],
                            cwd=city_dir, check=True
                        )
                    else:
                        logger.error(f"No charts found for task '{task}' at {qmd}")

        if flags['upload_enabled']:
            render_label = "render-" + "-".join(flags['render_targets'])
            upload_task_outputs(scan, task_name=render_label, files_before=files_before)
        return

    # =========================================================
    # RUN TASKS
    # =========================================================
    if os.path.isdir(city_dir):
        os.chdir(city_dir)
        # When -k or --scan-id is set, run the city's own tasks/ code (not
        # canonical). TASK_REGISTRY was built from canonical at startup, so
        # rewire sys.path and clear the module cache; run_task's
        # importlib.import_module then resolves to mnt/<city>/tasks/*.
        if flags['keep_as_is'] or flags['scan_id']:
            canonical_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if canonical_root in sys.path:
                sys.path.remove(canonical_root)
            sys.path.insert(0, city_dir)
            for k in list(sys.modules.keys()):
                if k == 'tasks' or k.startswith('tasks.'):
                    del sys.modules[k]
            import importlib
            importlib.invalidate_caches()

    # Determine tasks
    task_names = [a for a in args if not a.startswith("-") and a != scan_id]
    if flags['run_all']:
        simple_aliases = {k for k, v in ALIASES.items() if isinstance(v, str)}
        task_names = [name for name in TASK_REGISTRY
                      if menu_enabled(scan.menu, name) and name not in simple_aliases]
    # Auto-discover tasks with multianalysis files when --multianalysis and no tasks specified
    if step == "multianalysis" and not task_names:
        from pathlib import Path
        tasks_dir = Path(__file__).parent
        for task_dir in sorted(tasks_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            if any((task_dir / f"multianalysis{ext}").exists() for ext in [".R", ".py"]):
                task_names.append(task_dir.name)

    if not task_names:
        print("  No tasks to run.")
        return

    # Validate task names
    unknown = [t for t in task_names if t not in TASK_REGISTRY]
    if unknown:
        for t in unknown:
            logger.error(f"Unknown task: '{t}'. Did you mean one of: {', '.join(sorted(TASK_REGISTRY.keys()))}?")
        return

    task_names = topo_sort(task_names)

    # Config summary
    print(f"\n  City:      {scan.city_inputs.get('city_name', scan.city_name)}")
    print(f"  Country:   {scan.country_name} ({scan.country_iso3})")
    print(f"  Scan ID:   {scan.cityscan_id}")
    print(f"\n  Tasks: {', '.join(task_names)}")

    # Authenticate
    from core.config.auth import init_gee, init_gcs
    skip_tasks = set()

    gee_needed = GEE_TASKS & set(task_names)
    gcs_needed = GCS_TASKS & set(task_names)

    if gee_needed:
        try:
            init_gee()
            print(f"  GEE:       authenticated")
        except Exception:
            print(f"  GEE:       not authenticated — {len(gee_needed)} tasks will be skipped")
            skip_tasks |= GEE_TASKS

    if gcs_needed:
        try:
            init_gcs()
            print(f"  GCS:       authenticated")
        except Exception:
            print(f"  GCS:       not authenticated — {len(gcs_needed)} tasks will be skipped")
            skip_tasks |= GCS_TASKS

    print(f"  {'─'*40}\n")

    # Upload inputs once per run (static; not part of the per-task diff)
    if flags['upload_enabled']:
        from core.py.gcs_module import upload_inputs
        upload_inputs(scan)

    # --- Run tasks ---
    if flags['parallel_mode'] and len(task_names) > 1:
        from core.config.multitask import run_parallel
        all_results = run_parallel(
            task_names, scan, step=step,
            run_task_fn=run_task, skip_tasks=skip_tasks,
            auto_exit=flags['auto_exit']
        )
    else:
        from core.py.gcs_module import get_all_files, upload_task_outputs
        all_results = {}

        for name in task_names:
            if name in skip_tasks:
                logger.warning(f"Skipping '{name}' (auth not available)")
                all_results[name] = "skipped"
                continue

            files_before = get_all_files(scan.output_dir) | get_all_files(scan.render_dir) if flags['upload_enabled'] else None

            # Per-task exception isolation — matches multitask.py:319-333 behavior.
            # Without this, a single subprocess.CalledProcessError (e.g. missing R
            # package) propagates up and kills every remaining task in serial mode.
            try:
                results = run_task(name, scan, step=step)
            except Exception as e:
                logger.error(f"Task '{name}' failed with error: {type(e).__name__}: {e}")
                results = {"error": str(e)}
            all_results[name] = results

            if flags['upload_enabled']:
                upload_task_outputs(scan, name, step=step, files_before=files_before)

    # =========================================================
    # SUMMARY & REPORT
    # =========================================================
    if all_results and len(all_results) > 1:
        logger.info(f"\n{'='*50}\n  SUMMARY\n{'='*50}\n")

        phases = []
        for phase in ["collect", "analyze", "visualize"]:
            if any(phase in r for r in all_results.values() if isinstance(r, dict)):
                phases.append(phase)

        col_w = 12
        header = f"  {'task':<20}" + "".join(f"{p:>{col_w}}" for p in phases)
        logger.info(header)
        logger.info(f"  {'─'*20}" + "".join(f"{'─'*col_w}" for _ in phases))

        for name, result in all_results.items():
            if isinstance(result, str):
                row = f"  {name:<20}" + f"{'SKIP':>{col_w}}" * len(phases)
            else:
                row = f"  {name:<20}" + "".join(f"{result.get(p, '—'):>{col_w}}" for p in phases)
            logger.info(row)

        print()

    # Write/update task report to logs/task_report.txt
    if all_results:
        from datetime import datetime
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        report_path = os.path.join(os.path.dirname(str(scan.input_dir)), "logs", "task_report.txt")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)

        # Read existing report rows (keyed by "task|step")
        existing = {}
        if os.path.exists(report_path):
            with open(report_path) as f:
                for line in f:
                    parts = line.rstrip().split('|')
                    if len(parts) >= 5 and parts[0].strip() and not parts[0].strip().startswith('=') and not parts[0].strip().startswith('─') and parts[0].strip() != 'task':
                        key = f"{parts[0].strip()}|{parts[1].strip()}"
                        existing[key] = line.rstrip()

        # Build new rows from current results
        phases = []
        for phase in ["collect", "analyze", "visualize"]:
            if any(phase in r for r in all_results.values() if isinstance(r, dict)):
                phases.append(phase)

        for name, result in all_results.items():
            if isinstance(result, str):
                key = f"{name}|—"
                existing[key] = f"{name:<20} | {'—':<10} | {result:<8} | {'':<18} | {'':<30} | {now_str}"
                continue
            msgs = result.get("_messages", {})
            source = result.get("_source", "")
            for phase in phases:
                status = result.get(phase, "—")
                phase_msgs = msgs.get(phase, [])
                msg = (phase_msgs[0][:30] if phase_msgs else "").replace('|', '/')
                src = source if phase == phases[0] else ""
                key = f"{name}|{phase}"
                existing[key] = f"{name:<20} | {phase:<10} | {status:<8} | {src:<18} | {msg:<30} | {now_str}"

        # Write full report
        lines = []
        lines.append(f"Task Report: {scan.cityscan_id}")
        lines.append(f"{'='*110}")
        lines.append(f"{'task':<20} | {'step':<10} | {'status':<8} | {'source':<18} | {'message':<30} | {'last update'}")
        lines.append(f"{'─'*20}-+-{'─'*10}-+-{'─'*8}-+-{'─'*18}-+-{'─'*30}-+-{'─'*16}")

        # Sort by task name then phase
        phase_order = {"collect": 0, "analyze": 1, "visualize": 2, "—": 3}
        sorted_keys = sorted(existing.keys(), key=lambda k: (k.split('|')[0], phase_order.get(k.split('|')[1], 9)))

        for key in sorted_keys:
            lines.append(existing[key])

        lines.append(f"{'─'*110}")

        with open(report_path, 'w') as f:
            f.write('\n'.join(lines) + '\n')
        logger.info(f"Task report saved to: {report_path}")


if __name__ == "__main__":
    main()
