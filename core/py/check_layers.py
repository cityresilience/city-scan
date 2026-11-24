"""Check which spatial layers expected by layers.yml exist in the output."""

import os
import re
import yaml
from glob import glob
from core.config.paths import PROJECT_ROOT
from core.py.log_module import setup_logger

logger = setup_logger(__name__)

LAYERS_YML = PROJECT_ROOT / "source" / "layers.yml"


def check_layers(spatial_dir, output_dir=None):
    """Check spatial files against layers.yml patterns.

    Prints a summary table and saves a CSV to {output_dir}/log/.
    Returns the number of missing layers (excluding those with no pattern).
    """
    with open(LAYERS_YML) as f:
        layers = yaml.safe_load(f)

    spatial_files = [os.path.basename(p) for p in glob(os.path.join(spatial_dir, "*"))]

    rows = []
    for key, val in layers.items():
        pattern = val.get("fuzzy_string")
        if pattern:
            found = any(re.search(pattern, f) for f in spatial_files)
        else:
            found = False
        rows.append((key, pattern or "", found))

    # Print table
    found_rows = [(k, p, f) for k, p, f in rows if f]
    missing_rows = [(k, p, f) for k, p, f in rows if not f and p]
    no_pattern = [(k, p, f) for k, p, f in rows if not p]

    logger.info(f"Layer check: {len(found_rows)} found, {len(missing_rows)} missing, {len(no_pattern)} no pattern")

    col_w = max(len(r[0]) for r in rows)
    pat_w = max(len(r[1]) for r in rows) if rows else 10
    header = f"  {'layer':<{col_w}}  {'pattern':<{pat_w}}  found"
    sep = "  " + "-" * (col_w + pat_w + 10)

    print(f"\n{header}")
    print(sep)
    for key, pattern, found in sorted(rows, key=lambda r: (r[2], r[0])):
        status = "OK" if found else "MISSING" if pattern else "N/A"
        print(f"  {key:<{col_w}}  {pattern:<{pat_w}}  {status}")
    print()

    # Save CSV
    if output_dir:
        log_dir = os.path.join(output_dir, "log")
        os.makedirs(log_dir, exist_ok=True)
        csv_path = os.path.join(log_dir, "layer_check.csv")
        with open(csv_path, "w") as f:
            f.write("layer,pattern,found\n")
            for key, pattern, found in rows:
                f.write(f"{key},{pattern},{found}\n")
        logger.info(f"Layer check saved to {csv_path}")

    return len(missing_rows)
