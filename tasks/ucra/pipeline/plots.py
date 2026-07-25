from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ucra.config import load_config

SCRIPTS = [
    "cckp.R",
    "landslide.R",
    "heat.R",
    "drought.R",
    "air.R",
    "spei.R",
    "slr.R",
]


def resolve_rscript(rscript_arg: str) -> str:
    candidate = Path(rscript_arg)
    if candidate.is_file():
        return str(candidate)

    found = shutil.which(rscript_arg)
    if found:
        return found

    raise FileNotFoundError(
        "Rscript was not found. Pass the full path with "
        '--rscript "C:\\Program Files\\R\\R-4.4.1\\bin\\Rscript.exe"'
    )


def resolve_root() -> Path:
    candidates = [ROOT, Path.cwd()]
    for base in candidates:
        if (base / "r_scripts").exists() and (base / "src").exists():
            return base.resolve()
    return ROOT.resolve()


def main() -> None:
    root = resolve_root()

    parser = argparse.ArgumentParser(description="Run all R plotting scripts for a UCRA project.")
    parser.add_argument("--config", default="configs/ucra_menu.yaml", help="Path to YAML config.")
    parser.add_argument("--project-dir", default=None, help="Override project_dir from config.")
    parser.add_argument("--rscript", default="Rscript", help="Rscript executable name or full path")
    parser.add_argument(
        "--scripts",
        nargs="*",
        default=SCRIPTS,
        help="Optional subset of R scripts to run, e.g. --scripts heat.R slr.R",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path

    cfg = load_config(config_path)
    project_dir = Path(args.project_dir or cfg["project_dir"]).resolve()
    rscript_exe = resolve_rscript(args.rscript)

    if not project_dir.exists():
        raise FileNotFoundError(f"Project directory not found: {project_dir}")

    plots_dir = project_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, str]] = []

    for script_name in args.scripts:
        script_path = root / "r_scripts" / script_name

        if not script_path.exists():
            print(f"Skipping missing script: {script_path}")
            results.append((script_name, "MISSING SCRIPT"))
            continue

        cmd = [rscript_exe, str(script_path), str(project_dir)]
        print("Running:", " ".join(cmd))

        try:
            subprocess.run(cmd, check=True, cwd=project_dir)
            results.append((script_name, "OK"))
        except subprocess.CalledProcessError as exc:
            print(f"Failed: {script_name} (exit code {exc.returncode})")
            results.append((script_name, f"FAILED ({exc.returncode})"))

    print("\nPlot run summary:")
    for script_name, status in results:
        print(f"{script_name}: {status}")


if __name__ == "__main__":
    main()
