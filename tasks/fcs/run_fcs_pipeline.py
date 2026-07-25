"""Robust orchestration layer for the FCS city analytics pipeline.

This runner keeps the existing analytical functions intact while adding:
- per-step status tracking (SUCCESS, SKIPPED, FAILED)
- graceful continuation when inputs are missing for a city
- concise end-of-run summaries written to CSV and JSON
- structured logging to console and file
- lightweight preflight checks for common missing-input cases
- reduced log noise from unrelated ratio warnings and plotting libraries
"""
from __future__ import annotations
import argparse
import importlib
import json
import logging
import sys
import time
import warnings
from dataclasses import asdict, dataclass, field
logging.getLogger('fiona').setLevel(logging.ERROR)
logging.getLogger('fiona._env').setLevel(logging.ERROR)
logging.getLogger('pyproj').setLevel(logging.ERROR)
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable
ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / 'src'
for _path in (ROOT_DIR, SRC_DIR):
    if _path.exists() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
warnings.filterwarnings('ignore', message="One or several characters couldn't be converted correctly from UTF-8 to ISO-8859-1.*")
warnings.filterwarnings('ignore', category=FutureWarning, message='.*Neither gdal.UseExceptions\\(\\) nor gdal.DontUseExceptions\\(\\) has been explicitly called.*')
try:
    from osgeo import gdal as _bootstrap_gdal
    _bootstrap_gdal.DontUseExceptions()
except Exception:
    pass
import geopandas as gpd
import pandas as pd
import yaml
from utils import set_paths
LOGGER = logging.getLogger('city_pipeline')
WGS84_EPSG = 4326

def configure_runtime_behavior() -> None:
    """Reduce third-party runtime noise without altering pipeline logic."""
    warnings.filterwarnings('ignore', message="One or several characters couldn't be converted correctly from UTF-8 to ISO-8859-1.*")
    warnings.filterwarnings('ignore', category=FutureWarning, message='.*Neither gdal.UseExceptions\\(\\) nor gdal.DontUseExceptions\\(\\) has been explicitly called.*')
    try:
        from osgeo import gdal
        gdal.DontUseExceptions()
    except Exception:
        pass

@dataclass(frozen=True)
class PipelinePaths:
    """Container for frequently used pipeline directories."""
    base_dir: Path
    data: Path
    shapefiles: Path
    maps: Path
    rasters: Path
    output: Path
    tables: Path
    logs: Path

@dataclass
class PipelineContext:
    """Runtime context shared by pipeline steps."""
    config_path: Path
    config: dict
    paths: PipelinePaths
    country: str
    country_iso3: str
    city: str
    aoi_path: Path
    aoi_gdf: gpd.GeoDataFrame
    country_boundary_path: Path
    run_id: str

@dataclass(frozen=True)
class PipelineStep:
    """Describe a runnable pipeline step."""
    name: str
    description: str
    target: str
    runner: Callable[['PipelineRunner'], dict[str, Any] | None]

@dataclass
class StepResult:
    """Structured record of one pipeline step outcome."""
    name: str
    status: str
    duration_s: float
    description: str = ''
    message: str = ''
    error_type: str | None = None
    error_message: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)

class MissingDatasetError(RuntimeError):
    """Raised when a pipeline step should be skipped due to absent inputs."""

class PipelineRunner:
    """Coordinates and safely executes all pipeline steps."""

    def __init__(self, context: PipelineContext, modules: SimpleNamespace):
        """Initialize the runner with runtime context, imported modules, and the step registry."""
        self.ctx = context
        self.modules = modules
        self.steps = self._build_steps()
        self.results: list[StepResult] = []

    def _build_steps(self) -> dict[str, PipelineStep]:
        """Build the ordered registry of pipeline steps."""
        return {
            'population_rescaling': PipelineStep('population_rescaling', 'Prepare updated SSP population scaling factors.', 'section_1_population.create_updated_ssp3_dataset', PipelineRunner.run_population_rescaling),
            'population': PipelineStep('population', 'Export city population dynamics rasters and tables.', 'section_1_population.export_popdynamics', PipelineRunner.run_population),
            'gdp_rescaling': PipelineStep('gdp_rescaling', 'Prepare updated SSP GDP scaling factors.', 'section_2_gdp.create_updated_ssp3_dataset', PipelineRunner.run_gdp_rescaling),
            'gdp': PipelineStep('gdp', 'Export city GDP rasters and tables.', 'section_2_gdp.export_gdp', PipelineRunner.run_gdp),
            'urbanland': PipelineStep('urbanland', 'Export urban land statistics.', 'section_3_urbanland.export_urbanland', PipelineRunner.run_urbanland),
            'heatflux': PipelineStep('heatflux', 'Export anthropogenic heat flux indicators.', 'section_4_heatflux.export_heatflux', PipelineRunner.run_heatflux),
            'urbanheatisland': PipelineStep('urbanheatisland', 'Export urban heat island indicators.', 'section_5_urbanheatisland.export_urbanheatisland', PipelineRunner.run_urban_heat_island),
            'cckp_precipitation': PipelineStep('cckp_precipitation', 'Export and plot CCKP precipitation signals.', 'section_6_cckp.export_cckp_data', PipelineRunner.run_cckp_precipitation),
            'cckp_temperature': PipelineStep('cckp_temperature', 'Export and plot CCKP temperature signals.', 'section_6_cckp.export_cckp_data', PipelineRunner.run_cckp_temperature),
            'flood_population_exposure': PipelineStep('flood_population_exposure', 'Prepare Fathom flood layers and compute population exposure.', 'section_8_infra_demographic_flood_exposure.conduct_pop_exposure', PipelineRunner.run_flood_population_exposure),
            'flood_infrastructure_exposure': PipelineStep('flood_infrastructure_exposure', 'Compute road network exposure to flooding.', 'section_8_infra_demographic_flood_exposure.conduct_infra_exposure_analysis', PipelineRunner.run_flood_infrastructure_exposure),
            'cleanup': PipelineStep('cleanup', 'Run light post-processing cleanup for flood folders.', 'section_8_infra_demographic_flood_exposure.post_process_dir_cleaning', PipelineRunner.run_cleanup),
            'demographics': PipelineStep('demographics', 'Generate demographic projections and charts.', 'section_9_demographics.demographic_projection', PipelineRunner.run_demographics),
            'cyclones': PipelineStep('cyclones', 'Generate tropical cyclone wind-speed outputs.', 'section_10_cyclones.get_wind_speed', PipelineRunner.run_cyclones),
            'erosion': PipelineStep('erosion', 'Generate erosion tables, points, and transects.', 'section_11_erosion.process_erosion', PipelineRunner.run_erosion),
            'country_population_ratio': PipelineStep('country_population_ratio', 'Export country-level population rasters and city-to-country ratios.', 'section_1_1_population.export_popdynamics', PipelineRunner.run_country_population_ratio),
            'country_gdp_ratio': PipelineStep('country_gdp_ratio', 'Export country-level GDP rasters and city-to-country ratios.', 'section_2_1_gdp.export_gdp', PipelineRunner.run_country_gdp_ratio),
        }

    def default_step_order(self) -> list[str]:
        """Return the default execution order for a full pipeline run."""
        return ['population_rescaling', 'population', 'gdp_rescaling', 'gdp', 'urbanland', 'heatflux', 'urbanheatisland', 'cckp_precipitation', 'cckp_temperature', 'flood_population_exposure', 'flood_infrastructure_exposure', 'cleanup', 'demographics', 'cyclones', 'erosion', 'country_population_ratio', 'country_gdp_ratio']

    def run(self, selected_steps: Iterable[str] | None=None) -> list[StepResult]:
        """Execute the requested pipeline steps and persist the run summary."""
        requested = list(selected_steps) if selected_steps else self.default_step_order()
        unknown = [step for step in requested if step not in self.steps]
        if unknown:
            raise ValueError(f"Unknown step(s): {', '.join(unknown)}. Available steps: {', '.join(self.steps)}")
        LOGGER.info('RUN  pipeline                      city=%s | country=%s | run_id=%s', self.ctx.city, self.ctx.country, self.ctx.run_id)
        for step_name in requested:
            self.results.append(self._run_step(self.steps[step_name]))
        self._write_run_summary()
        self._log_final_summary()
        return self.results

    def _run_step(self, step: PipelineStep) -> StepResult:
        """Execute one pipeline step and return its structured result."""
        LOGGER.info('RUN  %-28s %s', step.name, step.target)
        start = time.time()
        try:
            summary = step.runner(self) or {}
            result = StepResult(name=step.name, description=step.description, status='SUCCESS', duration_s=round(time.time() - start, 2), message='Completed successfully.', summary=summary)
            LOGGER.info('DONE %-28s %7.2fs | %s', step.name, result.duration_s, _format_console_summary(summary))
            LOGGER.debug('[%s] %s', step.name, _format_summary(summary))
            return result
        except MissingDatasetError as exc:
            result = StepResult(name=step.name, description=step.description, status='SKIPPED', duration_s=round(time.time() - start, 2), message=str(exc), error_type=type(exc).__name__, error_message=str(exc))
            LOGGER.warning('SKIP %-28s %7.2fs | %s', step.name, result.duration_s, exc)
            return result
        except Exception as exc:
            result = StepResult(name=step.name, description=step.description, status='FAILED', duration_s=round(time.time() - start, 2), message='Step failed.', error_type=type(exc).__name__, error_message=str(exc))
            LOGGER.exception('FAIL %-28s %7.2fs | %s', step.name, result.duration_s, exc)
            return result

    def _write_run_summary(self) -> None:
        """Write the machine-readable run summary to JSON and CSV files."""
        summary_json = self.ctx.paths.logs / f'pipeline_run_summary_{self.ctx.run_id}.json'
        summary_csv = self.ctx.paths.logs / f'pipeline_run_summary_{self.ctx.run_id}.csv'
        with summary_json.open('w', encoding='utf-8') as handle:
            json.dump([asdict(result) for result in self.results], handle, indent=2, default=str)
        rows = []
        for result in self.results:
            rows.append({'name': result.name, 'status': result.status, 'duration_s': result.duration_s, 'description': result.description, 'message': result.message, 'error_type': result.error_type, 'error_message': result.error_message, 'summary_json': json.dumps(result.summary, default=str)})
        pd.DataFrame(rows).to_csv(summary_csv, index=False)
        LOGGER.debug('Saved run summary JSON: %s', summary_json)
        LOGGER.debug('Saved run summary CSV: %s', summary_csv)

    def _log_final_summary(self) -> None:
        """Write a concise end-of-run summary to the logger."""
        success = sum((r.status == 'SUCCESS' for r in self.results))
        skipped = sum((r.status == 'SKIPPED' for r in self.results))
        failed = sum((r.status == 'FAILED' for r in self.results))
        LOGGER.info('DONE pipeline                      success=%s | skipped=%s | failed=%s', success, skipped, failed)
        for result in self.results:
            LOGGER.debug('STEP %-28s %-7s %7.2fs | %s', result.name, result.status, result.duration_s, result.message)

    def run_population_rescaling(self) -> dict[str, Any]:
        """Create the population rescaling table required by the city population step."""
        self._require_files([self.ctx.paths.data / 'demographic' / 'SspDb_country_data_2013-06-12.csv', self.ctx.paths.data / 'demographic' / '1706548837040-ssp_basic_drivers_release_3.0_full.csv', self.ctx.paths.data / 'demographic' / 'GC_countries' / f'GC_{self.ctx.country_iso3}.csv'], 'population rescaling inputs')
        self.modules.section_1_population.create_updated_ssp3_dataset(self.ctx.country_iso3, self.ctx.country, self.ctx.city, ['demographic'], str(self.ctx.paths.data), str(self.ctx.paths.tables))
        out_csv = self.ctx.paths.tables / f'{self.ctx.country}_{self.ctx.city}_IIASA-WiC POP 2023_rescaled.csv'
        self._require_files([out_csv], 'population rescaling output')
        df = pd.read_csv(out_csv)
        return {'output_csv': str(out_csv), 'rows': len(df), 'scenarios': sorted(df.get('SCENARIO', pd.Series(dtype=str)).dropna().unique().tolist())}

    def run_population(self) -> dict[str, Any]:
        """Export city-level population rasters and the consolidated population summary table."""
        self._require_section_inputs('popdynamics', ('.tif',))
        self.modules.section_1_population.export_popdynamics(shp=str(self.ctx.aoi_path), vector_file=self.ctx.aoi_gdf, stat=['sum'], section=['popdynamics'], data=str(self.ctx.paths.data), tables=str(self.ctx.paths.tables), rasters=str(self.ctx.paths.rasters), country=self.ctx.country, city=self.ctx.city)
        out_csv = self.ctx.paths.tables / f'{self.ctx.country}_{self.ctx.city}_popdynamics.csv'
        self._require_files([out_csv], 'population output table')
        df = pd.read_csv(out_csv)
        return _pivot_summary(df, str(out_csv))

    def run_gdp_rescaling(self) -> dict[str, Any]:
        """Create the GDP rescaling table required by the city GDP step."""
        self._require_files([self.ctx.paths.data / 'demographic' / 'SspDb_country_data_2013-06-12.csv', self.ctx.paths.data / 'demographic' / '1706548837040-ssp_basic_drivers_release_3.0_full.csv', self.ctx.paths.data / 'demographic' / 'gdp_deflator.csv', self.ctx.paths.data / 'demographic' / 'GC_countries' / f'GC_{self.ctx.country_iso3}.csv'], 'GDP rescaling inputs')
        self.modules.section_2_gdp.create_updated_ssp3_dataset(self.ctx.country_iso3, self.ctx.country, self.ctx.city, ['demographic'], str(self.ctx.paths.data), str(self.ctx.paths.tables))
        out_csv = self.ctx.paths.tables / f'{self.ctx.country}_{self.ctx.city}_IIASA GDP 2023_rescaled.csv'
        self._require_files([out_csv], 'GDP rescaling output')
        df = pd.read_csv(out_csv)
        return {'output_csv': str(out_csv), 'rows': len(df), 'scenarios': sorted(df.get('SCENARIO', pd.Series(dtype=str)).dropna().unique().tolist())}

    def run_gdp(self) -> dict[str, Any]:
        """Export city-level GDP rasters and the consolidated GDP summary table."""
        self._require_section_inputs('gdp', ('.tif',))
        self.modules.section_2_gdp.export_gdp(shp=str(self.ctx.aoi_path), vector_file=self.ctx.aoi_gdf, stat=['sum'], section=['gdp'], data=str(self.ctx.paths.data), tables=str(self.ctx.paths.tables), rasters=str(self.ctx.paths.rasters), country=self.ctx.country, city=self.ctx.city)
        out_csv = self.ctx.paths.tables / f'{self.ctx.country}_{self.ctx.city}_gdp.csv'
        self._require_files([out_csv], 'GDP output table')
        df = pd.read_csv(out_csv)
        return _pivot_summary(df, str(out_csv))

    def run_urbanland(self) -> dict[str, Any]:
        """Export the urban land summary table for the configured city."""
        self._require_section_inputs('urbanland', ('.tif',))
        self.modules.section_3_urbanland.export_urbanland(shp=str(self.ctx.aoi_path), vector_file=self.ctx.aoi_gdf, stat=['mean'], section=['urbanland'], data=str(self.ctx.paths.data), tables=str(self.ctx.paths.tables), rasters=str(self.ctx.paths.rasters), country=self.ctx.country, city=self.ctx.city)
        out_csv = self.ctx.paths.tables / f'{self.ctx.country}_{self.ctx.city}_urbanland.csv'
        self._require_files([out_csv], 'urbanland table')
        df = pd.read_csv(out_csv)
        return _pivot_summary(df, str(out_csv))

    def run_heatflux(self) -> dict[str, Any]:
        """Export anthropogenic heat flux summary outputs for the configured city."""
        self._require_section_inputs('heatflux', ('.tif',))
        self.modules.section_4_heatflux.export_heatflux(shp=str(self.ctx.aoi_path), vector_file=self.ctx.aoi_gdf, stat=['mean'], section=['heatflux'], data=str(self.ctx.paths.data), tables=str(self.ctx.paths.tables), rasters=str(self.ctx.paths.rasters), country=self.ctx.country, city=self.ctx.city)
        out_csv = self.ctx.paths.tables / f'{self.ctx.country}_{self.ctx.city}_heatflux.csv'
        self._require_files([out_csv], 'heatflux table')
        df = pd.read_csv(out_csv)
        return _pivot_summary(df, str(out_csv))

    def run_urban_heat_island(self) -> dict[str, Any]:
        """Export urban heat island summary outputs for the configured city."""
        self._require_section_inputs('urbanheatisland', ('.tif',))
        self.modules.section_5_urbanheatisland.export_urbanheatisland(shp=str(self.ctx.aoi_path), vector_file=self.ctx.aoi_gdf, stat=['mean'], section=['urbanheatisland'], data=str(self.ctx.paths.data), tables=str(self.ctx.paths.tables), rasters=str(self.ctx.paths.rasters), country=self.ctx.country, city=self.ctx.city)
        out_csv = self.ctx.paths.tables / f'{self.ctx.country}_{self.ctx.city}_urbanheatisland.csv'
        self._require_files([out_csv], 'urban heat island table')
        df = pd.read_csv(out_csv)
        return _pivot_summary(df, str(out_csv))

    def run_cckp_precipitation(self) -> dict[str, Any]:
        """Export precipitation-related CCKP panel data and charts."""
        return self._run_cckp_section('Precipitation')

    def run_cckp_temperature(self) -> dict[str, Any]:
        """Export temperature-related CCKP panel data and charts."""
        return self._run_cckp_section('Temperature')

    def run_flood_population_exposure(self) -> dict[str, Any]:
        """Prepare Fathom flood layers and calculate population exposure outputs."""
        cfg = self.ctx.config.get('flood', {})
        flood_source = Path(self.ctx.config.get('flood_source', self.ctx.paths.data / 'fathom')) / self.ctx.country
        self._require_existing_dir(flood_source, 'Fathom flood input folder')
        processed_population = list(self.ctx.paths.rasters.glob('*processed_popdynamics*.tif'))
        if not processed_population:
            raise MissingDatasetError('Flood population exposure requires processed population rasters, but none were found in the rasters directory.')
        flood_bins = [15, 30, 50, 100]
        revised_bins_list = flood_bins.copy()
        self.modules.section_8_infra_demographic_flood_exposure.preprocess_fathom(str(self.ctx.paths.output), self.ctx.city, self.ctx.aoi_gdf, self.ctx.country)
        exposure_df = self.modules.section_8_infra_demographic_flood_exposure.conduct_pop_exposure(output=str(self.ctx.paths.output), tables=str(self.ctx.paths.tables), rasters=str(self.ctx.paths.rasters), vector_file=self.ctx.aoi_gdf, revised_bins_list=revised_bins_list, flood_bins=flood_bins, numberCategories=len(flood_bins), city=self.ctx.city, country=self.ctx.country)
        self.modules.section_8_infra_demographic_flood_exposure.create_pop_exposure_barchart(exposure_df, revised_bins_list, 'hsv', str(self.ctx.paths.maps))
        panel_csv = self.ctx.paths.tables / f'{self.ctx.city}_population_exposure_to_flood_panel_revised.csv'
        summary = {'output_csv': str(panel_csv), 'rows': int(len(exposure_df)), 'years': sorted(_series_unique(exposure_df, 'Year')), 'ssps': sorted(_series_unique(exposure_df, 'SSP'))}
        if '%Exposed population' in exposure_df.columns:
            summary['max_exposed_pct'] = round(float(exposure_df['%Exposed population'].max()), 2)
            summary['mean_exposed_pct'] = round(float(exposure_df['%Exposed population'].mean()), 2)
        return summary

    def run_flood_infrastructure_exposure(self) -> dict[str, Any]:
        """Calculate road-network exposure to flooding for the configured city."""
        cfg = self.ctx.config.get('flood', {})
        roads_shp = self.ctx.paths.shapefiles / f'{self.ctx.city}_road_network_shapefile.shp'
        self._require_files([roads_shp], 'road network shapefile required for infrastructure exposure')
        exposure_dir = self.ctx.paths.output / 'exposure'
        self._require_existing_dir(exposure_dir, 'flood exposure intermediate output folder')
        flood_bins = [15, 30, 50, 100]
        revised_bins_list = flood_bins.copy()
        self.modules.section_8_infra_demographic_flood_exposure.conduct_infra_exposure_analysis(output=str(self.ctx.paths.output), tables=str(self.ctx.paths.tables), shapefiles=str(self.ctx.paths.shapefiles), flood_bins=flood_bins, flood_years=cfg['year'], rps=cfg['rps'], flood_ssps=cfg['ssp'], city=self.ctx.city, country=self.ctx.country)
        self.modules.section_8_infra_demographic_flood_exposure.export_infra_exposure_barcharts(str(self.ctx.paths.tables), revised_bins_list, 'turbo', str(self.ctx.paths.maps), self.ctx.city, self.ctx.country)
        out_csv = self.ctx.paths.tables / f'{self.ctx.city}_road_network_fathom_exposure_mosaic_max_panel_gdal.csv'
        self._require_files([out_csv], 'road exposure output table')
        df = pd.read_csv(out_csv)
        pct_cols = [c for c in df.columns if c.startswith('Percentage of road flooded more than')]
        summary = {'output_csv': str(out_csv), 'rows': len(df), 'years': sorted(_series_unique(df, 'Year')), 'return_periods': sorted(_series_unique(df, 'Return period'))}
        if pct_cols:
            summary['max_road_exposure_pct'] = round(float(df[pct_cols].max().max()), 2)
        return summary

    def run_cleanup(self) -> dict[str, Any]:
        """Remove temporary flood-processing folders after exposure outputs are written."""
        removable = ['Coastal', 'Pluvial', 'Fluvial']
        existing = [name for name in removable if (self.ctx.paths.output / name).exists()]
        self.modules.section_8_infra_demographic_flood_exposure.post_process_dir_cleaning(str(self.ctx.paths.output), removable)
        removed = [name for name in existing if not (self.ctx.paths.output / name).exists()]
        return {'removed_directories': removed}

    def run_demographics(self) -> dict[str, Any]:
        """Generate demographic projections, charts, and output tables."""
        self._require_files([self.ctx.paths.data / 'demographic' / 'SspDb_country_data_2013-06-12.csv', self.ctx.paths.data / 'demographic' / 'GC_countries' / f'GC_{self.ctx.country_iso3}.csv'], 'demographic inputs')
        section = ['demographic']
        city_pop_ssp2, country_pop_ssp2 = self.modules.section_9_demographics.demographic_projection(city=self.ctx.city, country_iso3=self.ctx.country_iso3, country=self.ctx.country, ssp_to_use='SSP2', section=section, data=str(self.ctx.paths.data))
        city_pop_ssp5, country_pop_ssp5 = self.modules.section_9_demographics.demographic_projection(city=self.ctx.city, country_iso3=self.ctx.country_iso3, country=self.ctx.country, ssp_to_use='SSP5', section=section, data=str(self.ctx.paths.data))
        city_pop = pd.concat([city_pop_ssp2, city_pop_ssp5], ignore_index=True)
        country_pop = pd.concat([country_pop_ssp2, country_pop_ssp5], ignore_index=True)
        city_pop = city_pop.loc[city_pop['Year'] <= 2070].reset_index(drop=True)
        country_pop = country_pop.loc[country_pop['Year'] <= 2070].reset_index(drop=True)
        for ssp in ['SSP2', 'SSP5']:
            self.modules.section_9_demographics.pop_lineplot(city_pop, ssp, section, str(self.ctx.paths.maps), self.ctx.city, self.ctx.country)
            for year1, year2 in zip([2020, 2050], [2050, 2070]):
                self.modules.section_9_demographics.pyramid(city_pop, year1, year2, ssp, section, str(self.ctx.paths.maps), self.ctx.city, self.ctx.country)
        city_out = self.ctx.paths.tables / f'{self.ctx.country}_{self.ctx.city}_demographic_projection_city.csv'
        country_out = self.ctx.paths.tables / f'{self.ctx.country}_{self.ctx.city}_demographic_projection_country.csv'
        city_pop.to_csv(city_out, index=False)
        country_pop.to_csv(country_out, index=False)
        return {'city_rows': len(city_pop), 'country_rows': len(country_pop), 'city_output_csv': str(city_out), 'country_output_csv': str(country_out)}

    def run_cyclones(self) -> dict[str, Any]:
        """Generate tropical cyclone wind-speed tables and charts."""
        self._require_section_inputs('tropicalcyclones', ('.tif',))
        section = ['tropicalcyclones']
        output_cyclone = self.modules.section_10_cyclones.get_wind_speed(str(self.ctx.paths.tables), str(self.ctx.paths.data), self.ctx.aoi_gdf, section, self.ctx.country, self.ctx.city)
        self.modules.section_10_cyclones.visualize_results(str(self.ctx.paths.maps), section, output_cyclone, self.ctx.country, self.ctx.city)
        out_csv = self.ctx.paths.tables / f'{self.ctx.country}_{self.ctx.city}_{section[0]}_wind.csv'
        self._require_files([out_csv], 'cyclone output table')
        return {'output_csv': str(out_csv), 'rows': len(output_cyclone), 'max_current': float(output_cyclone['Current'].max())}

    def run_erosion(self) -> dict[str, Any]:
        """Generate erosion tables, shoreline points, and transect outputs."""
        self._require_section_inputs('globalerosion', ('.csv',))
        section = ['globalerosion']
        erosion_df = self.modules.section_11_erosion.process_erosion(str(self.ctx.paths.tables), str(self.ctx.paths.data), section, str(self.ctx.aoi_path), self.ctx.country, self.ctx.city)
        self.modules.section_11_erosion.map_storms(erosion_df, str(self.ctx.aoi_path))
        points = self.modules.section_11_erosion.create_points(self.ctx.country, str(self.ctx.paths.shapefiles), erosion_df)
        transect_gdf, gdf_sorted = self.modules.section_11_erosion.create_shorelines_transect(self.ctx.country, str(self.ctx.paths.shapefiles), erosion_df, 'no_temporal_cumulative')
        self.modules.section_11_erosion.trasfer_attributes_to_transects(self.ctx.country, str(self.ctx.paths.shapefiles), transect_gdf, gdf_sorted, 'no_temporal_cumulative')
        out_csv = self.ctx.paths.tables / f'{self.ctx.country}_{self.ctx.city}_{section[0]}_erosion.csv'
        self._require_files([out_csv], 'erosion output table')
        return {'output_csv': str(out_csv), 'rows': len(erosion_df), 'point_features': len(points), 'transects': len(transect_gdf)}

    def run_country_population_ratio(self) -> dict[str, Any]:
        """Export country population rasters and calculate city-to-country population ratios."""
        self._require_section_inputs('popdynamics', ('.tif',))
        self.modules.section_1_1_population.export_popdynamics(shp=str(self.ctx.country_boundary_path), vector_file=self.ctx.aoi_gdf, stat=['sum'], section=['popdynamics'], data=str(self.ctx.paths.data), tables=str(self.ctx.paths.tables), rasters=str(self.ctx.paths.rasters), country=self.ctx.country, city=self.ctx.city)
        return self._export_city_country_ratios(section_prefix='popdynamics_', city_prefix='processed_', country_prefix=f'{self.ctx.country}_processed_', output_csv=self.ctx.paths.tables / 'popdynamics_city_to_country_ratios.csv', ratio_label='ratio')

    def run_country_gdp_ratio(self) -> dict[str, Any]:
        """Export country GDP rasters and calculate city-to-country GDP ratios."""
        self._require_section_inputs('gdp', ('.tif',))
        self.modules.section_2_1_gdp.export_gdp(shp=str(self.ctx.country_boundary_path), vector_file=self.ctx.aoi_gdf, stat=['sum'], section=['gdp'], data=str(self.ctx.paths.data), tables=str(self.ctx.paths.tables), rasters=str(self.ctx.paths.rasters), country=self.ctx.country, city=self.ctx.city)
        return self._export_city_country_ratios(section_prefix='gdp_', city_prefix='processed_', country_prefix=f'{self.ctx.country}_processed_', output_csv=self.ctx.paths.tables / 'gdp_city_to_country_ratios.csv', ratio_label='gdp_ratio')

    def _run_cckp_section(self, section_name: str) -> dict[str, Any]:
        """Run a single CCKP extraction section and return its summary metrics."""
        self._require_section_inputs(section_name, ('.nc',))
        data = self.modules.section_6_cckp.export_cckp_data(self.ctx.aoi_gdf, [section_name], str(self.ctx.paths.data), str(self.ctx.paths.tables), self.ctx.country, self.ctx.city)
        self.modules.section_6_cckp.export_cckp_graph(df=data, x_var_name='time', y_var_names='Variable', section=[section_name], maps=str(self.ctx.paths.maps), country=self.ctx.country, city=self.ctx.city)
        out_csv = self.ctx.paths.tables / f'{self.ctx.country}_{self.ctx.city}_{section_name}_panel.csv'
        self._require_files([out_csv], f'CCKP {section_name} panel output')
        return {'output_csv': str(out_csv), 'rows': len(data), 'variables': sorted(_series_unique(data, 'Variable')), 'ssps': sorted(_series_unique(data, 'SSP'))}

    def _export_city_country_ratios(self, section_prefix: str, city_prefix: str, country_prefix: str, output_csv: Path, ratio_label: str) -> dict[str, Any]:
        """Match city and country rasters by suffix and export their ratio table."""
        raster_files = [p for p in self.ctx.paths.rasters.glob('*.tif')]
        city_files: dict[str, Path] = {}
        country_files: dict[str, Path] = {}
        for raster_path in raster_files:
            name = raster_path.name
            if name.startswith(city_prefix):
                suffix = name[len(city_prefix):]
                if suffix.startswith(section_prefix):
                    city_files[suffix] = raster_path
            elif name.startswith(country_prefix):
                suffix = name[len(country_prefix):]
                if suffix.startswith(section_prefix):
                    country_files[suffix] = raster_path
        rows: list[dict[str, Any]] = []
        missing_suffixes: list[str] = []
        for suffix, city_path in sorted(city_files.items()):
            country_path = country_files.get(suffix)
            if not country_path:
                missing_suffixes.append(suffix)
                continue
            ratio_value = _safe_raster_ratio(city_path, country_path)
            rows.append({'city_raster': city_path.name, 'country_raster': country_path.name, ratio_label: ratio_value})
        if not rows:
            raise MissingDatasetError(f"No matching city/country raster pairs were found for section prefix '{section_prefix}'.")
        pd.DataFrame(rows).to_csv(output_csv, index=False)
        if missing_suffixes:
            LOGGER.warning("Skipped %s unmatched '%s' raster(s) while building %s.", len(missing_suffixes), section_prefix.rstrip('_'), output_csv.name)
        LOGGER.info('Saved ratio table: %s', output_csv)
        ratios = [row[ratio_label] for row in rows]
        return {'output_csv': str(output_csv), 'matched_pairs': len(rows), 'unmatched_city_rasters': len(missing_suffixes), 'min_ratio': min(ratios), 'max_ratio': max(ratios)}

    def _require_section_inputs(self, section_name: str, suffixes: tuple[str, ...]) -> Path:
        """Validate that a section input folder exists and contains supported files."""
        folder = self.ctx.paths.data / section_name
        self._require_existing_dir(folder, f"section input folder '{section_name}'")
        files = [p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in tuple((s.lower() for s in suffixes))]
        if not files:
            raise MissingDatasetError(f"No supported input files found for section '{section_name}' in {folder}. Expected one of: {', '.join(suffixes)}")
        return folder

    def _require_existing_dir(self, path: Path, description: str) -> None:
        """Validate that a required directory exists before a step runs."""
        if not path.exists() or not path.is_dir():
            raise MissingDatasetError(f'Missing {description}: {path}')

    def _require_files(self, paths: list[Path], description: str) -> None:
        """Validate that one or more required files exist before a step runs."""
        missing = [str(path) for path in paths if not path.exists()]
        if missing:
            raise MissingDatasetError(f"Missing {description}: {'; '.join(missing)}")

def _series_unique(df: pd.DataFrame, column: str) -> list[Any]:
    """Return the non-null unique values from a DataFrame column."""
    if column not in df.columns:
        return []
    return [value for value in df[column].dropna().unique().tolist()]

def _pivot_summary(df: pd.DataFrame, output_csv: str) -> dict[str, Any]:
    """Create a compact summary dictionary for pivot-style output tables."""
    summary = {'output_csv': output_csv, 'rows': len(df)}
    if 'Scenario' in df.columns:
        summary['scenarios'] = sorted(df['Scenario'].dropna().unique().tolist())
    year_like = [col for col in df.columns if str(col).isdigit()]
    if year_like:
        summary['year_columns'] = year_like
    return summary

def _format_summary(summary: dict[str, Any]) -> str:
    """Return a detailed summary string for file logging."""
    if not summary:
        return 'no summary'
    return '; '.join((f'{key}={value}' for key, value in summary.items()))


def _format_console_summary(summary: dict[str, Any]) -> str:
    """Return a compact summary string for console output."""
    if not summary:
        return 'no summary'
    compact: list[str] = []
    if 'output_csv' in summary:
        compact.append(f"output={Path(summary['output_csv']).name}")
    for key in ('rows', 'matched_pairs', 'unmatched_city_rasters', 'point_features', 'transects', 'city_rows', 'country_rows'):
        if key in summary:
            compact.append(f'{key}={summary[key]}')
    for key in ('scenarios', 'year_columns', 'variables', 'ssps', 'years', 'return_periods', 'removed_directories'):
        value = summary.get(key)
        if isinstance(value, list):
            compact.append(f'{key}={len(value)}')
    for key in ('max_exposed_pct', 'mean_exposed_pct', 'max_road_exposure_pct', 'max_current', 'min_ratio', 'max_ratio'):
        if key in summary:
            value = summary[key]
            if isinstance(value, float):
                compact.append(f'{key}={value:.2f}')
            else:
                compact.append(f'{key}={value}')
    return ' | '.join(compact) if compact else 'completed'


def _safe_raster_ratio(city_raster: Path, country_raster: Path) -> float:
    """Return the ratio of summed values between a city raster and a country raster."""
    from osgeo import gdal
    import numpy as np

    def _sum_raster(path: Path) -> float:
        """Return the summed value of a raster band as a float."""
        ds = gdal.Open(str(path))
        if ds is None:
            raise FileNotFoundError(f'Could not open raster: {path}')
        arr = ds.GetRasterBand(1).ReadAsArray()
        ds = None
        return float(np.nansum(arr))
    city_sum = _sum_raster(city_raster)
    country_sum = _sum_raster(country_raster)
    if country_sum == 0:
        raise ValueError(f'Country raster sum is zero for {country_raster.name}')
    return city_sum / country_sum

def setup_logging(level: str='INFO', log_dir: Path | None=None, run_id: str | None=None) -> Path | None:
    """Configure concise console logging and detailed file logging for a pipeline run."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)

    log_file = None
    file_handler: logging.Handler | None = None
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f'pipeline_run_{run_id or datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s'))
        root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter('%(message)s'))

    city_logger = logging.getLogger('city_pipeline')
    city_logger.handlers.clear()
    city_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    city_logger.propagate = False
    city_logger.addHandler(console_handler)
    if file_handler is not None:
        city_logger.addHandler(file_handler)

    logging.getLogger('matplotlib').setLevel(logging.ERROR)
    logging.getLogger('matplotlib.category').setLevel(logging.ERROR)
    logging.getLogger('fiona').setLevel(logging.ERROR)
    logging.getLogger('fiona._env').setLevel(logging.ERROR)
    logging.getLogger('rasterio').setLevel(logging.ERROR)
    logging.getLogger('PIL').setLevel(logging.ERROR)
    logging.getLogger('osgeo').setLevel(logging.ERROR)
    return log_file


def load_yaml_config(config_path: Path) -> dict:
    """Load a YAML configuration file into a dictionary."""
    with config_path.open('r', encoding='utf-8') as file:
        return yaml.safe_load(file)

def import_section_modules() -> SimpleNamespace:
    """Import all pipeline section modules and return them as a namespace."""
    module_names = ['section_1_population', 'section_1_1_population', 'section_2_gdp', 'section_2_1_gdp', 'section_3_urbanland', 'section_4_heatflux', 'section_5_urbanheatisland', 'section_6_cckp', 'section_7_extremeheat', 'section_8_infra_demographic_flood_exposure', 'section_9_demographics', 'section_10_cyclones', 'section_11_erosion', 'section_12_post_processing']
    imported: dict[str, object] = {}
    for name in module_names:
        try:
            imported[name] = importlib.import_module(f'src.{name}')
        except ModuleNotFoundError:
            imported[name] = importlib.import_module(name)
    return SimpleNamespace(**imported)

def build_context(config_path: Path, cfg: dict | None=None) -> PipelineContext:
    """Build the runtime context used by the pipeline runner."""
    cfg = cfg or load_yaml_config(config_path)
    base_dir = Path(cfg['base_dir'])
    data, shapefiles, maps, rasters, output, tables = set_paths(str(base_dir))
    logs = Path(output) / 'logs'
    paths = PipelinePaths(base_dir=base_dir, data=Path(data), shapefiles=Path(shapefiles), maps=Path(maps), rasters=Path(rasters), output=Path(output), tables=Path(tables), logs=logs)
    aoi_path = Path(cfg['AOI_path'])
    aoi_gdf = gpd.read_file(aoi_path).to_crs(epsg=WGS84_EPSG)
    country_source = Path(cfg.get('AOI_path_countries', paths.shapefiles / 'WB_countries_Admin0_10m.shp'))
    all_countries = gpd.read_file(country_source)
    country_name = cfg['country_name']
    country_gdf = all_countries.loc[all_countries['NAME_EN'] == country_name]
    if country_gdf.empty:
        raise ValueError(f"Country '{country_name}' not found in {country_source}")
    country_boundary_path = paths.shapefiles / f'{country_name}.shp'
    country_gdf.to_file(country_boundary_path)
    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    return PipelineContext(config_path=config_path, config=cfg, paths=paths, country=country_name, country_iso3=cfg['country_iso3'], city=cfg['city_name'], aoi_path=aoi_path, aoi_gdf=aoi_gdf, country_boundary_path=country_boundary_path, run_id=run_id)

def get_enabled_steps_from_config(cfg: dict, default_steps: list[str]) -> list[str]:
    """Return enabled pipeline steps from the YAML config, preserving pipeline order."""
    step_flags = cfg.get('pipeline_steps')
    if not isinstance(step_flags, dict):
        return default_steps
    enabled = [step for step in default_steps if step_flags.get(step, True)]
    return enabled or default_steps

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the pipeline runner."""
    parser = argparse.ArgumentParser(description='Run the robust FCS city analytics pipeline.')
    parser.add_argument('--config', default='fcs_menue.yaml', help='Path to the YAML configuration file.')
    parser.add_argument('--steps', nargs='*', help='Optional list of step names to run. If omitted, the full pipeline runs.')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], help='Logging verbosity.')
    return parser.parse_args()

def main() -> None:
    """Run the command-line entry point for the pipeline runner."""
    args = parse_args()
    configure_runtime_behavior()
    cfg = load_yaml_config(Path(args.config))
    import os
    os.environ['FCS_CONFIG_PATH'] = str(Path(args.config).resolve())
    base_dir = Path(cfg['base_dir'])
    log_dir = base_dir / '02-process-output' / 'logs'
    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = setup_logging(args.log_level, log_dir=log_dir, run_id=run_id)
    if log_file:
        LOGGER.info('LOG  pipeline                      %s', log_file)
    context = build_context(Path(args.config), cfg=cfg)
    context.run_id = run_id
    modules = import_section_modules()
    runner = PipelineRunner(context, modules)
    configured_steps = None if args.steps else get_enabled_steps_from_config(cfg, runner.default_step_order())
    runner.run(args.steps or configured_steps)
if __name__ == '__main__':
    main()
