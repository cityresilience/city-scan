# GCS Data Sources

## Buckets

| Bucket | Access | Auth |
|---|---|---|
| `city-scan-global-public` | Public | None — use `https://storage.googleapis.com/city-scan-global-public/` or `/vsicurl/` |
| `city-scan-global-data` | Private | Requires `gcloud auth` — use `googleCloudStorageR::gcs_get_object()` for CSVs, `/vsigs/` for rasters |
| `city-scan-global-private` | Private | Requires `gcloud auth` — use `/vsigs/` |

## Public bucket (`city-scan-global-public`)

| Dataset | GCS path | Task | Access |
|---|---|---|---|
| Air quality PM2.5 | `air_quality/` | air_quality | `/vsicurl/` |
| FABDEM elevation | `fabdem/` | elevation | `/vsicurl/` |
| GHSL tile schema | `ghsl/GHSL2_0_MWD_L1_tile_schema_land.shp` | ghs_builtup, ghs_population | `/vsicurl/` |
| GlobFire | `globfire_fgb/` | burned_area | `https://` |
| Gridded GDP 1990-2022 | `Gridded_GDP_1990_2022/` | gridded_gdp | `/vsicurl/` |
| Landslide susceptibility | `landslide/` | landslide | `/vsicurl/` |
| Liquefaction | `liquefaction/` | liquefaction | `/vsicurl/` |
| NASA FWI (daily) | `nasa_fwi/` | fwi | `/vsicurl/` |
| Relative Wealth Index | `relative_wealth_index/` | rwi | `pd.read_csv()` |
| Solar PVOUT | `solar/` | solar | `/vsicurl/` |
| Urban Centre Database | `Urban_Centre_Database/` | benchmark-worldpop | `/vsicurl/` |
| WB countries admin | `wb_countries/` | aoi lookup | `/vsicurl/` |
| WorldPop Global 1 | `world_population/` | worldpop | `urllib` download |
| WorldPop Global 2 | `world_population/WorldPop-Global-2/` | worldpop | `/vsicurl/` |
| WorldPop age structures | `world_population_age_structures/` | demographics | `/vsicurl/` |

## Private bucket (`city-scan-global-data`)

| Dataset | GCS path | Task | Access |
|---|---|---|---|
| Oxford Economics CSV | `oxford-economics/Oxford Global Cities Data.csv` | oxford | `gcs_get_object()` |
| Oxford areas | `oxford-economics/oxford-economics-areas.csv` | oxford | `gcs_get_object()` |
| Oxford locations | `oxford-economics/oxford-locations.csv` | benchmark-helper | `gcs_get_object()` |
| Köppen climate CSV | `climate-classification/Koeppen-Geiger-ASCII.csv` | basic_info | Python `storage.Client` |
| UN data population | `Population/undata-pop.csv` | pop-backup | `gcs_get_object()` |
| Flood archive | `flood-archive/FloodArchive_region.shp` | flood_events | `/vsigs/` |
| Cyclone archive (IBTrACS) | `IBTrACS-tropical-cyclones/IBTrACS.since1980.list.v04r00.lines.shp` | cyclones | `/vsigs/` |
| Coastal erosion | `Long-term Shoreline Changes/ShorelineMonitor_1984_2016_v1.1_set3_filtered.csv` | coastal_erosion | `gcs_get_object()` |
| ESA CCI landcover | `ESACCI.tif` | landcover_burn | `/vsigs/` |
| Solar PV (monthly) | `globalsolar/PVOUT-monthly.tif` | solar (R charting) | `/vsigs/` |
| SLR projections | `SLR/` | sea_level_rise | `/vsigs/` |
| WB countries admin | `wb_countries_admin0_10m/` | R aoi lookup | `/vsigs/` |

## Private bucket (`city-scan-global-private`)

| Dataset | GCS path | Task | Access |
|---|---|---|---|
| Fathom flood tiles | `Fathom/v2023/` | fathom | `/vsigs/` |
| WSF Tracker tiles | `wsf_tracker/` | wsf | `/vsigs/` |
