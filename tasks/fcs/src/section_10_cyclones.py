"""Tropical cyclone processing and visualization functions for wind speed return-period analysis."""
import rasterio
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.ticker import ScalarFormatter

def get_wind_speed(tables, data, gdf, section, country, city):
    """Sample cyclone wind-speed rasters for the city and export the return-period summary table."""
    city_centroid = gdf.iloc[0]['geometry'].centroid
    coords = [(city_centroid.x, city_centroid.y)]
    coords += [x for x in gdf.iloc[0]['geometry'].exterior.coords]
    output = pd.DataFrame()
    all_rps = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 500, 600, 700, 800, 900, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]
    all_regions = ['EP', 'NA', 'NI', 'SI', 'SP', 'WP']
    max_vals = []
    for rp in all_rps:
        vals = []
        for region in all_regions:
            raster_file = os.path.join(data, f'{section[0]}/STORM_current/FIXED_RP/STORM_FIXED_RETURN_PERIODS_{region}_{rp}_YR_RP.tif')
            src = rasterio.open(raster_file)
            vals.append([x for x in src.sample(coords)])
        max_vals.append(np.max(vals))
    output['RPs'] = all_rps
    output['Current'] = max_vals
    all_gcms = ['CMCC-CM2-VHR4', 'CNRM-CM6-1-HR', 'EC-Earth3P-HR', 'HADGEM3-GC31-HM']
    for gcm in all_gcms:
        max_vals = []
        for rp in all_rps:
            vals = []
            for region in all_regions:
                raster_file = os.path.join(data, f'{section[0]}/STORM_climate_change/FIXED_RP/{gcm}/STORM_FIXED_RETURN_PERIODS_{gcm}_{region}_{rp}_YR_RP.tif')
                src = rasterio.open(raster_file)
                vals.append([x for x in src.sample(coords)])
            max_vals.append(np.max(vals))
        output[gcm] = max_vals
    output.to_csv(f'{tables}/{country}_{city}_{section[0]}_wind.csv')
    return output

def visualize_results(maps, section, output, country, city):
    """Create and save the tropical cyclone wind-speed comparison chart."""
    all_gcms = ['CMCC-CM2-VHR4', 'CNRM-CM6-1-HR', 'EC-Earth3P-HR', 'HADGEM3-GC31-HM']
    output_climate = output[[x for x in output.columns if x != 'Current']]
    output_climate = pd.melt(output_climate, id_vars='RPs', value_vars=all_gcms)
    output_climate.columns = ['RPs', 'GCM', 'Wind speed']
    minval = np.unique(output[output.columns[1:]])[1]
    maxval = np.unique(output[output.columns[1:]])[-1]
    fig, ax = plt.subplots(figsize=(5, 5))
    sns.lineplot(data=output_climate, x='RPs', y='Wind speed', label='Climate change\n(2015-2050)', color='indianred', ax=ax)
    ax.plot(output['RPs'], output['Current'], label='Current\n(1980-2017)')
    ax.set_ylim(minval, maxval)
    plt.xscale('log')
    plt.legend(loc='upper left')
    ax.xaxis.set_major_formatter(ScalarFormatter())
    ax.set_xlabel('Return period', fontsize=12)
    ax.set_ylabel('Maximum wind speed (m/s)', fontsize=12)
    plt.title('Maximum tropical cyclone\nwind speed in {}'.format(city))
    plt.grid()
    if maxval > 32:
        ax.text(x=14000, y=32, s='-- Cat 1')
    if maxval > 42:
        ax.text(x=14000, y=42, s='-- Cat 2')
    if maxval > 49:
        ax.text(x=14000, y=49, s='-- Cat 3')
    if maxval > 58:
        ax.text(x=14000, y=58, s='-- Cat 4')
    if maxval > 70:
        ax.text(x=14000, y=70, s='-- Cat 5')
    plt.savefig(f'{maps}/{country}_{city}_{section[0]}_cyclone.jpeg', dpi=300, bbox_inches='tight')
    plt.close(fig)
