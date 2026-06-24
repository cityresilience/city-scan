"""
Task execution functions: run_task() and run_multicity().
"""
import sys
import os
import importlib
from pathlib import Path
from core.py.error_tracker import ErrorTracker
from core.py.log_module import setup_logger
from core.config.tasks import TASK_REGISTRY
from core.config.paths import OUTPUTS
from core.config.utils import slugify

logger = setup_logger(__name__)


def run_task(task_name, scan, step=None):
    """
    Run a single task. Returns a dict of phase results like:
      {"collect": "ok", "analyze": "fail", "visualize": "skip"}
    """
    if task_name not in TASK_REGISTRY:
        logger.error(f"Unknown task: {task_name}")
        return {"error": "unknown"}

    module_path, collect_fn, analyze_fn, visualize_fn, run_fn, charts_fn = TASK_REGISTRY[task_name]
    results = {}
    messages = {}

    logger.info(f"\n{'='*50}\n  {task_name.upper()}\n{'='*50}")

    try:
        module = importlib.import_module(module_path)
    except Exception as e:
        logger.error(f"[{task_name}] import failed: {e}")
        return {"error": str(e), "_messages": {"import": [str(e)]}}

    if step == "multianalysis":
        import subprocess
        task_dir = Path(module.__file__).parent
        results["multianalysis"] = "skip"
        for ext in [".R", ".py"]:
            ma_file = task_dir / f"multianalysis{ext}"
            if ma_file.exists():
                header = f"  {task_name}: multianalysis"
                logger.info(f"\n{header}\n  {'─' * (len(header) - 2)}")
                with ErrorTracker() as tracker:
                    if ext == ".R":
                        # Stream R output live AND capture for post-run error scan.
                        # Previously capture_output=True buffered everything so the
                        # terminal looked frozen during long R jobs (fathom, gdp_sectoral).
                        # Prepend `here` install check so fresh R installs self-heal:
                        # setup.R auto-installs `here`, but its first line already uses
                        # here::here() — chicken-and-egg. The inline check breaks the cycle.
                        r_src = f"if (!'here' %in% rownames(installed.packages())) install.packages('here', repos='https://cloud.r-project.org'); source(here::here('{ma_file.relative_to(task_dir.parent.parent)}'))"
                        proc = subprocess.Popen(
                            ["Rscript", "-e", r_src],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1,
                        )
                        r_output_lines = []
                        for line in proc.stdout:
                            print(line, end='')
                            r_output_lines.append(line)
                        proc.wait()
                        if proc.returncode != 0:
                            raise subprocess.CalledProcessError(proc.returncode, proc.args)
                        r_output = ''.join(r_output_lines)
                        if 'Error' in r_output and tracker.status == "OK":
                            tracker.warn("R script reported errors")
                    else:
                        exec(open(ma_file).read())
                results["multianalysis"] = tracker.status
                messages["multianalysis"] = tracker.messages
                print()
                break
    elif step:
        fn_map = {"collect": collect_fn, "analyze": analyze_fn, "visualize": visualize_fn}
        fn_name = fn_map.get(step)
        if fn_name is None:
            results[step] = "skip"
        else:
            header = f"  {task_name}: {step}"
            logger.info(f"\n{header}\n  {'─' * (len(header) - 2)}")
            with ErrorTracker() as tracker:
                getattr(module, fn_name)(scan)
            results[step] = tracker.status
            messages[step] = tracker.messages
            if tracker.messages:
                for msg in tracker.messages:
                    logger.error(f"  [{task_name}:{step}] {msg}")
            print()
    else:
        for phase, fn_name in [("collect", collect_fn), ("analyze", analyze_fn)]:
            if fn_name is None:
                results[phase] = "skip"
                continue
            header = f"  {task_name}: {phase}"
            logger.info(f"\n{header}\n  {'─' * (len(header) - 2)}")
            with ErrorTracker() as tracker:
                getattr(module, fn_name)(scan)
            results[phase] = tracker.status
            messages[phase] = tracker.messages
            if tracker.messages:
                for msg in tracker.messages:
                    logger.error(f"  [{task_name}:{phase}] {msg}")
            print()

    parts = [f"{phase}: {status}" for phase, status in results.items()]
    source = getattr(scan, 'sources', {}).get(task_name, '')
    source_str = f" [{source}]" if source else ""
    logger.info(f"  [{task_name}] {' | '.join(parts)}{source_str}\n")

    results["_messages"] = messages
    results["_source"] = source
    return results


def run_multicity(multicity_path, args, flags):
    """
    Read multi_inputs.yml, generate city_inputs.yml for each city,
    and run the pipeline sequentially.

    AOI subfolders live in inputs/AOI/ (user copies them there).
    For each city, auto-detects the .shp (non-wards) in the subfolder.
    Wards auto-detected from {subfolder}_wards/.
    """
    import yaml
    import subprocess
    import geopandas as gpd
    from core.config.scan import scan_init
    from core.config.inputs import prepare_inputs
    from core.py.aoi_module import find_country

    with open(multicity_path) as f:
        mc = yaml.safe_load(f)

    project_root = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    inputs_dir = project_root / "inputs"
    aoi_base = inputs_dir / "AOI"

    # Modes:
    #   multipolygon only → extract all rows as AOI, run all
    #   multipolygon + cities → extract all rows as AOI, run only those in cities list
    #   cities only → existing behavior (separate AOI folders)
    #   neither → error
    has_mp = 'multipolygon' in mc and mc['multipolygon']
    has_cities = 'cities' in mc and mc['cities']

    if not has_mp and not has_cities:
        raise ValueError("multi_inputs.yml must have either 'cities:' or 'multipolygon:' (or both)")

    if has_mp:
        mp_cfg = mc.pop('multipolygon')
        mp_file = Path(mp_cfg['file'])
        if not mp_file.is_absolute():
            mp_file = project_root / mp_file
        name_col = mp_cfg['name_column']

        logger.info(f"Reading multipolygon AOI from: {mp_file}")
        mp_gdf = gpd.read_file(mp_file)

        if name_col not in mp_gdf.columns:
            raise ValueError(f"Column '{name_col}' not found in {mp_file}. Available: {list(mp_gdf.columns)}")

        # Detect country from the multipolygon file
        mp_4326 = mp_gdf.to_crs(4326)
        _, mp_country, _ = find_country(aoi=mp_4326)

        # Filter to cities list if provided — validate all names exist in multipolygon
        run_filter = None
        if has_cities:
            all_mp_slugs = {slugify(str(row[name_col]).strip()) for _, row in mp_gdf.iterrows()}
            run_filter = set()
            for c in mc['cities']:
                slug = slugify(c['city_name'])
                if slug not in all_mp_slugs:
                    raise ValueError(f"City '{c['city_name']}' not found in multipolygon file. Available: {sorted(all_mp_slugs)}")
                run_filter.add(slug)
            logger.info(f"Filtering to cities: {', '.join(run_filter)}")

        # Extract all AOI shapefiles, build cities list
        all_mp_cities = []
        cities = []
        for _, row in mp_gdf.iterrows():
            city_name = str(row[name_col]).strip()
            city_slug = slugify(city_name)
            all_mp_cities.append(city_name)

            # Always extract AOI if not exists
            city_aoi_dir = aoi_base / city_slug
            city_aoi_dir.mkdir(parents=True, exist_ok=True)
            shp_path = city_aoi_dir / f"{city_slug}.shp"
            if not shp_path.exists():
                row_gdf = gpd.GeoDataFrame([row], crs=mp_gdf.crs)
                row_gdf.to_file(shp_path)
                logger.info(f"  Extracted: {city_name} -> {shp_path}")

            # Only add to run list if no filter or city is in filter
            if run_filter is None or city_slug in run_filter:
                cities.append({'city_name': city_name})

        mc.pop('cities', None)
    else:
        cities = mc.pop('cities')
        for c in cities:
            c['city_name'] = str(c['city_name']).strip()

    shared = dict(mc)

    all_city_names = [c['city_name'] for c in cities]

    print(f"\n  Multi-City Batch Run")
    print(f"  {'─'*40}")
    print(f"  Cities: {', '.join(all_city_names)}")
    print(f"  {'─'*40}\n")

    passthrough_args = [a for a in args if a != '--multicity']
    if '--parallel' in passthrough_args and '--auto-exit' not in passthrough_args:
        passthrough_args.append('--auto-exit')

    use_existing = flags['use_existing']
    override = bool(flags.get('sync_targets'))

    # Detect country from first city's AOI (all cities share the same country)
    mp_country = locals().get('mp_country', '')
    country_name = shared.get('country', '') or mp_country
    if not country_name:
        first_city = cities[0]['city_name']
        first_slug = slugify(first_city)
        for d in aoi_base.iterdir():
            if d.is_dir() and d.name.lower() in {first_city.lower(), first_slug}:
                shps = [f for f in d.glob("*.shp") if "wards" not in f.stem.lower()]
                if shps:
                    aoi_gdf = gpd.read_file(shps[0]).to_crs(4326)
                    _, country_name, _ = find_country(aoi=aoi_gdf)
                break

    for i, city_cfg in enumerate(cities):
        city_name = city_cfg['city_name']
        city_slug = slugify(city_name)

        # Find AOI subfolder
        candidates = {city_name.lower(), city_slug}
        aoi_dir = None
        for d in aoi_base.iterdir():
            if d.is_dir() and d.name.lower() in candidates:
                aoi_dir = d
                break

        if aoi_dir is None:
            logger.error(f"No AOI subfolder found for '{city_name}' in {aoi_base}")
            continue

        # Auto-detect AOI .shp (non-wards)
        shp_files = [f for f in aoi_dir.glob("*.shp") if "wards" not in f.stem.lower()]
        if not shp_files:
            logger.error(f"No AOI .shp found in {aoi_dir}")
            continue

        print(f"  [{i+1}/{len(cities)}] {city_name} ({aoi_dir.name}/{shp_files[0].stem})")

        # Build city_inputs
        city_inputs = dict(shared)
        for k, v in city_cfg.items():
            city_inputs[k] = v
        city_inputs['AOI_shp_name'] = shp_files[0].stem
        city_inputs['bm_cities_manual'] = [n for n in all_city_names if n != city_name]

        # Resolve scan_id
        scan_id = scan_init(country_name, city_slug, use_existing=use_existing)

        # Prepare inputs
        user_input_dir = OUTPUTS / scan_id / "01-user-input"
        wards_dir = aoi_base / f"{aoi_dir.name}_wards"
        prepare_inputs(
            dest=user_input_dir,
            city_inputs=city_inputs,
            source_dir=inputs_dir,
            aoi_dir=aoi_dir,
            wards_dir=wards_dir if wards_dir.exists() else None,
            override=override,
        )

        # Run pipeline with --scan-id
        cmd = [sys.executable, "-m", "tasks"] + passthrough_args + ["--scan-id", scan_id]
        result = subprocess.run(cmd, cwd=str(project_root))
        if result.returncode != 0:
            logger.error(f"City {city_name} failed with return code {result.returncode}")

    print(f"\n  {'═'*50}")
    print(f"  Multi-city batch complete: {len(cities)} cities")
    print(f"  {'═'*50}\n")
