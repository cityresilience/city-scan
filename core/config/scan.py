"""Scan class — city scan configuration and initialization."""
import os
import sys
import yaml
import geopandas as gpd
from datetime import datetime as dt
from .paths import INPUTS, OUTPUTS, PROJECT_ROOT
from .utils import slugify
from .inputs import prepare_inputs
from .sync import sync_project_files
from core.py.aoi_module import find_country
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


def scan_init(country_name, city_name, use_existing=False):
    """
    Find existing scan folder or build a new scan_id.

    Args:
        country_name: Lowercase country name (e.g. 'namibia'), or None for multi-country AOIs.
        city_name: Slugified city name (e.g. 'walvis_bay')
        use_existing: If True, auto-select existing folder without prompting.

    Returns:
        scan_id string like '2026-03-namibia-windhoek' or '2026-03-lobito_corridor'
    """
    # Country-scale scan (city IS the country): single-name suffix, no doubling
    if country_name == city_name:
        country_name = None
    suffix = f"-{country_name}-{city_name}" if country_name else f"-{city_name}"
    today_id = f"{dt.now().strftime('%Y-%m')}{suffix}"
    existing = sorted([
        d.name for d in OUTPUTS.iterdir()
        if d.is_dir() and d.name.endswith(suffix)
    ]) if OUTPUTS.exists() else []

    if not existing:
        return today_id
    elif today_id in existing:
        return today_id
    else:
        latest = existing[-1]
        if use_existing or not sys.stdin.isatty():
            logger.info(f"Using existing folder: {latest}")
            return latest
        else:
            print(f"\n  Found existing folder: {latest}")
            print(f"  Today's date would create: {today_id}")
            print(f"  [e] Use existing ({latest})")
            print(f"  [n] Create new ({today_id})")
            choice = input("  Choice (e/n): ").strip().lower()
            if choice == 'n':
                return today_id
            else:
                return latest


class Scan:
    def __init__(self, scan_id=None, sync_tasks=None, skip_sync=False,
                 use_existing=False, sync_targets=None):
        """
        Args:
            scan_id: Explicit scan ID (from --scan-id). If None, auto-detected.
            sync_tasks: List of task names to sync, or None for all.
            skip_sync: Skip project file syncing (e.g. --render mode).
            use_existing: Auto-select existing folder, skip folder prompt (-e).
            sync_targets: List of sync targets (e.g. ["tasks", "source"]), or None to prompt.
        """
        # --- Determine input source ---
        if scan_id:
            input_source = OUTPUTS / f'{scan_id}/01-user-input'
            self.cityscan_id = scan_id

            if not (input_source / "city_inputs.yml").exists():
                logger.info(f"No city_inputs.yml in {input_source}, copying from {INPUTS}")
                prepare_inputs(input_source, yaml.safe_load(open(INPUTS / "city_inputs.yml")), INPUTS)
        else:
            input_source = INPUTS

        # --- Load city inputs ---
        self.city_inputs_path = input_source / "city_inputs.yml"
        with open(self.city_inputs_path) as f:
            self.city_inputs = yaml.safe_load(f)

        self.city_name = slugify(self.city_inputs['city_name'])
        self.first_year = self.city_inputs['first_year']
        self.last_year = self.city_inputs['last_year']
        self.fwi_first_year = self.city_inputs.get('fwi_first_year')
        self.fwi_last_year = self.city_inputs.get('fwi_last_year')

        # Flood config
        flood_cfg = self.city_inputs.get("flood", {})
        self.flood_threshold = flood_cfg.get("threshold")
        self.flood_year = flood_cfg.get("year")
        self.flood_ssp = flood_cfg.get("ssp")
        self.flood_return_periods = flood_cfg.get("return_period", [])

        # --- Load AOI ---
        aoi_path = input_source / f"AOI/{self.city_inputs['AOI_shp_name']}.shp"
        self.aoi = gpd.read_file(aoi_path).to_crs(4326)
        logger.info(f'Successfully loaded AOI from: {aoi_path}')

        # --- Country lookup ---
        self.country_iso3, self.country_name, self.country_iso3_list = find_country(aoi=self.aoi)
        self.multi_country = len(self.country_iso3_list) > 1

        # --- Resolve scan_id if not provided ---
        if not scan_id:
            from .paths import _city_root
            if INPUTS.name == "01-user-input":
                self.cityscan_id = _city_root.name
            else:
                prev = self.city_inputs.get('prev_run_date', None)
                if prev is not None:
                    if self.multi_country:
                        self.cityscan_id = f"{prev}-{self.city_name}"
                    else:
                        self.cityscan_id = f"{prev}-{self.country_name}-{self.city_name}"
                else:
                    self.cityscan_id = scan_init(
                        self.country_name if not self.multi_country else None,
                        self.city_name,
                        use_existing=use_existing
                    )

        logger.info(f'Working on {self.cityscan_id}')

        # --- Directory paths ---
        self.city_dir = OUTPUTS / self.cityscan_id
        self.input_dir = OUTPUTS / f'{self.cityscan_id}/01-user-input'
        self.output_dir = OUTPUTS / f'{self.cityscan_id}/02-process-output'
        self.render_dir = OUTPUTS / f'{self.cityscan_id}/03-render-output'
        self.spatial_dir = f'{self.output_dir}/spatial'
        self.tabular_dir = f'{self.output_dir}/tabular'

        for d in [
            self.input_dir,
            f'{self.output_dir}/images/',
            self.spatial_dir,
            self.tabular_dir,
            self.render_dir,
            f'{self.render_dir}/plots/png',
            f'{self.render_dir}/plots/html',
        ]:
            os.makedirs(d, exist_ok=True)

        # --- Copy inputs if first run ---
        if not scan_id and not (self.input_dir / "city_inputs.yml").exists():
            logger.info(f"First run — copying inputs to {self.input_dir}")
            prepare_inputs(self.input_dir, self.city_inputs, INPUTS)

        # --- Sync project files ---
        if skip_sync:
            menu_path = input_source / "menu.yml"
            self.menu = yaml.safe_load(open(menu_path))
            self.font_dict = {'family': 'sans-serif', 'size': 12, 'color': 'black'}
            self.sources = {}
            return

        sync_project_files(
            self.city_dir,
            sync_targets=sync_targets,
            sync_tasks=sync_tasks,
        )

        # --- Load menu ---
        menu_path = input_source / "menu.yml"
        self.menu = yaml.safe_load(open(menu_path))

        # Data source tracking
        self.sources = {}

        # Plot font config
        self.font_dict = {
            'family': (
                'system-ui, -apple-system, "Segoe UI", Roboto, '
                '"Helvetica Neue", Arial, "Noto Sans", "Liberation Sans", '
                'sans-serif, "Apple Color Emoji", "Segoe UI Emoji", '
                '"Segoe UI Symbol", "Noto Color Emoji"'
            ),
            'size': 12,
            'color': 'black',
        }
