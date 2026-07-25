from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ucra.config import load_config
from ucra.ee_utils import initialize_earth_engine
from ucra.pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the modular UCRA pipeline.")
    parser.add_argument("--config", required=True, help="Path to YAML config file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)

    project_dir = cfg.get("project_dir")
    country = cfg.get("country")
    ee_project = cfg.get("ee_project")
    ee_auth_mode = cfg.get("ee_auth_mode", "notebook")
    ee_force_auth = bool(cfg.get("ee_force_auth", False))

    run_plots = bool(cfg.get("run_plots", False))
    rscript_path = cfg.get("rscript_path", "Rscript")
    plot_scripts = cfg.get("plot_scripts", [])

    if not project_dir:
        raise ValueError("Config must include 'project_dir'.")
    if not country:
        raise ValueError("Config must include 'country'.")

    initialize_earth_engine(
        project=ee_project,
        auth_mode=ee_auth_mode,
        force_auth=ee_force_auth,
    )

    run_pipeline(
        project_dir=project_dir,
        country=country,
        config_path=args.config,
    )

    if run_plots:
        plots_cmd = [
            sys.executable,
            str(ROOT / "plots.py"),
            "--config",
            args.config,
            "--rscript",
            rscript_path,
        ]

        if plot_scripts:
            plots_cmd.append("--scripts")
            plots_cmd.extend(plot_scripts)

        print("\nRunning plots automatically...")
        subprocess.run(plots_cmd, check=True)


if __name__ == "__main__":
    main()