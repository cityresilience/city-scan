"""Input preparation — write city_inputs.yml, copy AOI/menu/wards to 01-user-input/."""
import os
import shutil
import yaml
from pathlib import Path
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


def prepare_inputs(dest, city_inputs, source_dir, aoi_dir=None, wards_dir=None, override=False):
    """
    Prepare 01-user-input/ directory with city config, AOI, and menu.

    Args:
        dest: Path to 01-user-input/ directory
        city_inputs: dict of city configuration (written as city_inputs.yml)
        source_dir: Path to inputs/ directory (for menu.yml)
        aoi_dir: Path to AOI directory to copy from (flat directory of .shp etc.)
                 If None, uses source_dir/AOI/ with auto-detection.
        wards_dir: Path to wards directory to copy from, or None
        override: If True, overwrite existing files (-o flag)
    """
    os.makedirs(dest, exist_ok=True)

    # Write city_inputs.yml — always update to keep config in sync with multi_inputs
    ci_path = dest / "city_inputs.yml"
    with open(ci_path, 'w') as f:
        for key, val in city_inputs.items():
            yaml.dump({key: val}, f,
                      default_flow_style=False, allow_unicode=True, sort_keys=False)
            f.write('\n')

    # Copy menu.yml
    menu_src = source_dir / "menu.yml"
    menu_dst = dest / "menu.yml"
    if menu_src.exists() and (override or not menu_dst.exists()):
        shutil.copy2(menu_src, menu_dst)

    # Copy AOI files — only sidecars matching AOI_shp_name in city_inputs.yml
    aoi_dst = dest / "AOI"
    aoi_shp_name = city_inputs.get('AOI_shp_name')
    if aoi_dir and aoi_dir.exists() and (override or not aoi_dst.exists()):
        os.makedirs(aoi_dst, exist_ok=True)
        for f in aoi_dir.iterdir():
            if f.is_file() and f.stem == aoi_shp_name:
                shutil.copy2(f, aoi_dst / f.name)
    elif not aoi_dir:
        # Single city mode — separate AOI and wards from source_dir/AOI/
        aoi_src = source_dir / "AOI"
        if aoi_src.exists() and (override or not aoi_dst.exists()):
            os.makedirs(aoi_dst, exist_ok=True)
            for f in aoi_src.iterdir():
                if not f.is_file():
                    continue
                if 'wards' in f.stem.lower():
                    # Auto-detect wards into wards/ subfolder
                    w_dst = dest / "wards"
                    os.makedirs(w_dst, exist_ok=True)
                    shutil.copy2(f, w_dst / f.name)
                elif f.stem == aoi_shp_name:
                    shutil.copy2(f, aoi_dst / f.name)

    # Copy wards files
    if wards_dir and wards_dir.exists():
        w_dst = dest / "wards"
        if override or not w_dst.exists():
            os.makedirs(w_dst, exist_ok=True)
            for f in wards_dir.iterdir():
                if f.is_file():
                    shutil.copy2(f, w_dst / f.name)
