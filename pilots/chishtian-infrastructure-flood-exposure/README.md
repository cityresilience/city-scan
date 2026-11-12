# Chishtian infrastructure and flood exposure

Chishtian test case for review and approval before application to the other cities. Uses existing City Scan flood outputs to assess supplied water and sewerage infrastructure. It does not modify the existing flood-processing workflow.

Maps where supplied water and sewerage infrastructure overlaps modelled river and rainwater flooding.

```text
inputs/infrastructure/  Original client GIS delivery, kept once
inputs/flood/           Existing City Scan flood rasters and study boundary
inputs/basemap/         Carto Light map tiles and map font
flood_exposure.py       Calculate network lengths and facilities within flood footprints
maps.py                 Draw the map sheets
run.py                  Run the calculation and mapping together
verify.py               Check saved results independently against the flood raster cells
city_scan_collection.py Existing local City Scan flood collector, for source reference
outputs/                Maps, exposure table and GIS results
```

## Run

Use Python 3.11 with the packages in `requirements.txt`, then run:

```bash
python run.py
python verify.py
```

Paths are relative to this project; no workstation-specific paths are required. Calculations and rendering finish in a temporary folder before replacing the four generated outputs. Input or rendering failures therefore leave the previous results in place; replacement of all four files is not a single filesystem transaction. It was run using the existing `city-scan` Conda environment on WSL2 Linux; a fresh installation of the pinned dependencies has not been tested.

## Inputs

**Infrastructure:** the complete original client delivery is retained here, including its other cities and base maps. This workflow reads only the following Chishtian layers and the municipal boundary, with their shapefile companions:

- `Water Supply/Chishtian/Water_Supply_Lines.shp`: 213 water-network features.
- `Water Supply/Chishtian/Water_Resources.shp`: 48 water facilities.
- `Sewerage/Chishtian/Existing_Sewer_Lines.shp`: 608 sewer-network features.
- `Sewerage/Chishtian/Disposal_Station.shp`: four disposal/outfall points.
- `MC Boundary/Proposed_MC_Boundaries_PICP_Cities.shp`: municipal boundaries; select `Chistian`.

Stored GIS geometry is used. The water-facility Longitude field duplicates Latitude and is not used to locate facilities. The supplied delivery does not establish survey accuracy or completeness. Roads and canal/nullah layers provided context in earlier maps; these map sheets use Carto Light instead.

**Flooding:** `chishtian_fluvial_2020.tif` (river) and `chishtian_pluvial_2020.tif` (rainwater) are existing City Scan outputs derived from Fathom. They were already on the project workstation; they were not downloaded from GitHub for this assessment. Each contains `r10`, `r100` and `r1000` bands. RP means return period: 10, 100 and 1,000 years. Values are flood-footprint flags, not depths. The rasters use a 2020 baseline and approximately 30 m cells. `study_area.fgb` is the existing City Scan study boundary.

**Map background:** 42 cached Carto Light tiles, with the font used by the UCRA report. These affect presentation, not exposure calculations.

## Method and code origin

The existing flood-input workflow comes from [City Scan](https://github.com/cityresilience/city-scan), particularly `tasks/fathom/collection.py`. The unchanged local file is included as `city_scan_collection.py` for reference; it is not called by `run.py` and requires the full City Scan installation to execute. Its collector references Fathom `v2023`, fluvial undefended and pluvial defended products, with a 15 cm threshold. The original city configuration is retained as `inputs/flood/city_inputs.yml`. This project reads the resulting cached rasters; it does not download or process original Fathom tiles.

`flood_exposure.py`, `maps.py` and `run.py` are project-specific code. They reorganise the earlier `build_pilot.py` calculation and `render_report_style.py` presentation without changing the exposure method. They are not claimed to be upstream City Scan scripts. The exact City Scan commit that produced the cached flood rasters is unconfirmed because the working copy has broken Git metadata.

Positive flood cells are converted to polygons. Infrastructure and polygons are projected to UTM zone 43N (EPSG:32643), then intersected. Only intersecting pipe segments contribute to exposed length; intersecting facilities are counted. Combined exposure is the spatial union of river and rainwater footprints at the same return period, not a joint-event probability. All supplied assets are retained. Maps use EPSG:3857 for display.

## Results

- `outputs/maps.pdf`: two map sheets, water infrastructure and sewerage/sanitation infrastructure. The latter includes sewer lines, disposal stations and outfall chambers; no separate sanitation dataset was supplied or analysed.
- `outputs/maps_enlarged.pdf`: the same 12 panels at a larger size.
- `outputs/exposure.csv`: lengths, counts and coverage by hazard and return period.
- `outputs/exposure.gpkg`: assets with exposure attributes, exposed segments, flood footprints and boundaries; open in QGIS.

## Interpretation

Flooding shallower than 15 cm is excluded, although it may affect infrastructure. Separately, processed zero values conflate below-threshold flooding and NoData; zero overlap cannot confirm no exposure. Three water facilities fall outside the cached raster extent and remain unassessed. The client municipal boundary and City Scan study boundary have different extents; neither was shifted to force agreement.

This is a spatial exposure assessment. It does not model drainage capacity, pipe hydraulics, damage, contamination or service failure. No separate drainage network is assessed.

The supplied local project includes the inputs and results. `.gitignore` excludes those folders from code commits; public redistribution rights for the client GIS, Fathom-derived layers and presentation assets have not been established. Nothing has been published.

## Peer review

Review performed 12 November 2026. Project code was inspected for input handling, path portability, calculation logic, failure behaviour and unnecessary dependencies. Validation remains active with Python optimisation enabled. The retained City Scan collector is a reference snapshot: it was inspected but not executed against its private cloud inputs.

`verify.py` checks GeoPackage integrity, conservation of totals, increasing exposure across return periods, individual facility classifications and network lengths. Network exposure is checked by independently sampling the source raster every 0.5 m along each line, including the combined footprint. The maximum river/rainwater difference was 1.66 m. The full workflow was also rerun from outside the project directory. Inputs, exposure values and the rendered map pages were checked for unintended changes.

Remaining limits: no clean-machine installation test; no reconstruction from original Fathom tiles; no independent confirmation of survey accuracy or the original flood-processing commit. Passing these checks supports the implementation, not hydraulic-model validation or institutional approval.

For review, use one code repository and one data/results location:

- **GitHub:** `README.md`, `.gitignore`, `requirements.txt`, `run.py`, `flood_exposure.py`, `maps.py`, `verify.py` and `city_scan_collection.py`. Keep upstream attribution. Use a private repository for the initial review and a pull request for code comments and recorded review decisions.
- **SharePoint:** this README, the two map PDFs, `exposure.csv`, `exposure.gpkg` and the three `inputs/` subfolders, preserving their paths. Upload only the five listed infrastructure layers and their shapefile companions for this Chishtian assessment; the other cities and base maps are retained locally as the original delivery. Omit OS download tags named `:Zone.Identifier`. Colleagues who need to rerun the workflow can combine the GitHub code with these inputs.

Cross-link the repository and SharePoint folder once created. Record the reviewed Git commit and review decision together so the code and outputs remain identifiable. Revise files in the same locations rather than creating parallel packages. No additional archive or duplicate project folder is needed.
