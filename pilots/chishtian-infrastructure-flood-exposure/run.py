"""Combine the client GIS and existing flood rasters, then draw the maps."""
from pathlib import Path
from tempfile import TemporaryDirectory

import flood_exposure as exposure
import maps


def main():
    exposure.OUT.mkdir(exist_ok=True)
    output_folder = exposure.OUT
    # Finish calculations and rendering before replacing any existing results.
    with TemporaryDirectory(prefix='.run-', dir=output_folder) as work:
        try:
            exposure.OUT = maps.OUT = Path(work)
            _, boundary, study_area, assets = exposure.load_inputs()
            hazards, footprints, _ = exposure.load_hazards()
            exposure.save_layer(boundary, 'client_proposed_mc_boundary')
            exposure.save_layer(study_area, 'existing_city_scan_aoi')
            exposure.analyse(assets, hazards, footprints)
            maps.render_maps()
            for name in ['exposure.gpkg', 'exposure.csv', 'maps.pdf', 'maps_enlarged.pdf']:
                (Path(work) / name).replace(output_folder / name)
        finally:
            exposure.OUT = maps.OUT = output_folder
    print(f'Results: {output_folder}')


if __name__ == '__main__':
    main()
