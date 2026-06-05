"""CLI flag parsing — single source of truth for all flag logic."""

KNOWN_FLAGS = {
    "--collect", "--analyze", "--multianalysis", "--render",
    "--all", "--scan-id", "--multicity", "--parallel", "--auto-exit",
    "--upload", "--gcs", "--download", "--sync", "--keep", "--list", "--help", "--check",
    "-e", "-t", "-k",
}

DOWNLOAD_TARGETS = {"01", "02", "03"}

SYNC_TARGETS = {"tasks", "source", "core", "scan-calculations"}
CHECK_TARGETS = {"r", "python", "gee", "gcs", "quarto", "inputs"}


def parse_args(args):
    """Parse CLI args into a flags dict. Called once in __main__.py."""
    f = {}

    # --sync targets (tasks, source, core, scan-calculations)
    f['sync_targets'] = []
    if "--sync" in args or "-t" in args:
        if "-t" in args and "--sync" not in args:
            # -t is shortcut for --sync tasks
            f['sync_targets'] = ["tasks"]
        elif "--sync" in args:
            idx = args.index("--sync")
            for a in args[idx + 1:]:
                if a.startswith("-"):
                    break
                if a in SYNC_TARGETS:
                    f['sync_targets'].append(a)
                else:
                    break
            # --sync with no targets = sync everything
            if not f['sync_targets']:
                f['sync_targets'] = list(SYNC_TARGETS)

    # Behavior flags
    f['keep_as_is'] = "-k" in args or "--keep" in args
    f['use_existing'] = (
        "-e" in args or bool(f['sync_targets']) or f['keep_as_is']
    )
    f['upload_enabled'] = "--upload" in args

    # --gcs: connect to a scan stored in GCS. --download=01,02 is the explicit
    # pull (symmetric to --upload); bare --download pulls all folders.
    f['gcs'] = "--gcs" in args
    f['download'] = []
    for a in args:
        if a == "--download":
            f['download'] = list(DOWNLOAD_TARGETS)
        elif a.startswith("--download="):
            f['download'] = [v.strip() for v in a.split("=", 1)[1].split(",") if v.strip()]

    f['parallel_mode'] = "--parallel" in args
    f['auto_exit'] = "--auto-exit" in args
    f['run_all'] = "--all" in args
    f['multicity'] = "--multicity" in args

    # Step
    if "--collect" in args:
        f['step'] = "collect"
    elif "--analyze" in args:
        f['step'] = "analyze"
    elif "--multianalysis" in args:
        f['step'] = "multianalysis"
    else:
        f['step'] = None

    # --check targets (r, python, gee, gcs, quarto, inputs). No targets = all.
    f['check'] = "--check" in args
    f['check_targets'] = []
    if f['check']:
        idx = args.index("--check")
        for a in args[idx + 1:]:
            if a.startswith("-"):
                break
            if a in CHECK_TARGETS:
                f['check_targets'].append(a)
            else:
                break
        if not f['check_targets']:
            f['check_targets'] = list(CHECK_TARGETS)

    # --scan-id value
    f['scan_id'] = None
    if "--scan-id" in args:
        idx = args.index("--scan-id")
        if idx + 1 < len(args):
            f['scan_id'] = args[idx + 1]

    # --render targets
    f['render_targets'] = []
    if "--render" in args:
        idx = args.index("--render")
        valid_targets = {"maps", "scan-calculations", "charts"}
        for a in args[idx + 1:]:
            if a.startswith("--"):
                break
            if a in valid_targets:
                f['render_targets'].append(a)
            else:
                break

    # Task names (non-flag args, excluding --scan-id value, render targets, sync targets)
    skip_values = set()
    if f['scan_id']:
        skip_values.add(f['scan_id'])
    skip_values.update(f['render_targets'])
    skip_values.update(f['sync_targets'])
    skip_values.update(f['check_targets'])
    f['task_names'] = [a for a in args if not a.startswith("-") and a not in skip_values]

    return f


def validate_args(args):
    """Check for unknown flags. Returns error message or None."""
    for a in args:
        if a.startswith("--download="):
            for v in a.split("=", 1)[1].split(","):
                if v.strip() not in DOWNLOAD_TARGETS:
                    return f"--download values must be 01, 02, or 03 (got '{v.strip()}')"
            continue
        if a.startswith("-") and a not in KNOWN_FLAGS:
            return f"Unknown flag: '{a}'. Use --list flags to see available flags."
    # --gcs / --download
    if "--gcs" in args:
        if "--scan-id" not in args:
            return "--gcs requires --scan-id"
        if "--parallel" in args:
            return "--gcs cannot be combined with --parallel"
    if any(a == "--download" or a.startswith("--download=") for a in args) and "--gcs" not in args:
        return "--download requires --gcs"
    if "--render" in args:
        idx = args.index("--render")
        valid_targets = {"maps", "scan-calculations", "charts"}
        has_target = any(
            a in valid_targets
            for a in args[idx + 1:]
            if not a.startswith("--")
        )
        if not has_target:
            return "--render requires a target: maps, scan-calculations, or charts"
    if "--scan-id" in args:
        idx = args.index("--scan-id")
        if idx + 1 >= len(args):
            return "--scan-id requires a value"
    return None
