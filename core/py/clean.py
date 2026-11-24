#!/usr/bin/env python3
"""
tabular output csv cleanup script

Takes csv and tif files from existing City Scan tabular and spatial output and interim Scan Calculation Sheet data outputs and cleans up formatting and makes additional calculations so that the output is ready for visualization, returning new csv files:

"""

import pandas as pd
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
import geopandas as gpd
import os
import sys
from typing import Optional

# population growth
def clean_pg(input_file, output_file=None):
    """
    clean up population data (Oxford or World Pop format) for visualization as pg.csv.
    """
    import os
    
    # read the csv file
    df = pd.read_csv(input_file)
    
    # detect column names (handle both formats)
    year_col = 'Year' if 'Year' in df.columns else 'year' # where 'year' is the World Pop format and 'Year' is the Oxford format
    pop_col = 'Population' if 'Population' in df.columns else 'population'
    
    # sort by year to ensure correct order
    df = df.sort_values(year_col).reset_index(drop=True)
    
    # create new df with desired structure
    result_df = pd.DataFrame({
        'yearName': df[year_col],
        'population': df[pop_col]
    })
    
    # calculate population growth percentage
    result_df['populationGrowthPercentage'] = result_df['population'].pct_change() * 100
    result_df['populationGrowthPercentage'] = result_df['populationGrowthPercentage'].round(3)
    
    # create output filename if not provided
    if output_file is None:
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/pg.csv'
            
    # save the cleaned data
    result_df.to_csv(output_file, index=False)
    
    print(f"Cleaned data saved to: {output_file}")
    print(f"Years covered: {result_df['yearName'].min()} - {result_df['yearName'].max()}")
    print(f"Total data points: {len(result_df)}")
    print(f"Population range: {result_df['population'].min():,} - {result_df['population'].max():,}")
    
    return result_df

# population age sex
def clean_pas(input_file, output_file=None):
    """
    clean up the population age structure csv file (i.e., 2025-02-city-country_02-process-output_tabular_city_demographics.csv) for visualization as pas.csv.
    
    parameters:
    -----------
    input_file : str
        Path to the input csv file
    output_file : str, optional
        Path for output.
    """
    
    # read the population age structure csv file
    df = pd.read_csv(input_file)
    
    # combine "0-1" and "1-4" age brackets into "0-4"
    df['age_group'] = df['age_group'].replace({'0-1': '0-4', '1-4': '0-4'})
    
    # group by the new age brackets and sex, summing the population
    df_grouped = df.groupby(['age_group', 'sex'], as_index=False)['population'].sum()
    
    # create new df with desired structure, renaming columns appropriately
    result_df = pd.DataFrame({
        'ageBracket': df_grouped['age_group'],
        'sex': df_grouped['sex'].replace({'f': 'female', 'm': 'male'}),  # expand abbreviations
        'count': df_grouped['population'].round(2),  # round to 2 decimal places
        'percentage': (df_grouped['population'] / df_grouped['population'].sum() * 100).round(7),  # calculate percentage
        'yearName': 2021  # assuming 2021 based on most up-to-date data from data source as noted in the Scan Calculation Sheet
    })
    
    # sort by age bracket and sex for consistent ordering
    # get all unique age brackets from data and create a comprehensive sort order
    unique_brackets = sorted(result_df['ageBracket'].unique())
    
    # create a custom sort order that includes all brackets in data
    age_order = ['0-4', '5-9', '10-14', '15-19', '20-24', '25-29', 
                 '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', 
                 '65-69', '70-74', '75-79', '80+', '80']
    
    # add any missing brackets from data to the end of the order
    for bracket in unique_brackets:
        if bracket not in age_order:
            age_order.append(bracket)
    
    # create a categorical column for proper sorting, only including categories that exist in data
    existing_categories = [cat for cat in age_order if cat in unique_brackets]
    
    try:
        result_df['age_sort'] = pd.Categorical(result_df['ageBracket'], categories=existing_categories, ordered=True)
        result_df = result_df.sort_values(['age_sort', 'sex']).drop('age_sort').reset_index(drop=True)
        # remove the temporary "age_sort" column - ensure it's dropped
        if 'age_sort' in result_df.columns:
            result_df = result_df.drop('age_sort', axis=1)
    except Exception as e:
        print(f"Warning: Could not sort by age bracket ({e}). Using default sorting.")
        result_df = result_df.sort_values(['ageBracket', 'sex']).reset_index(drop=True)
    
   # final check to ensure "age_sort" column is not in the output
    if 'age_sort' in result_df.columns:
        result_df = result_df.drop('age_sort', axis=1)
   
    # create output filename if not provided
    if output_file is None:
        import os
        # ensure the processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/pas.csv' # saves to data/processed folder
            
    # save the cleaned data
    result_df.to_csv(output_file, index=False)
    
    print(f"Cleaned data saved to: {output_file}")
    print(f"Total population: {result_df['count'].sum():,.0f}")
    print(f"Age brackets: {result_df['ageBracket'].nunique()}")
    print(f"Sex categories: {result_df['sex'].nunique()}")
    print(f"Total records: {len(result_df)}")
    
    return result_df

# relative wealth index (rwi) % area with different relative wealth index levels - "Least wealthy", "Less wealthy", "Average wealth", "More wealthy", "Most wealthy")
def clean_rwi_area(input_gpkg_file: str, output_file: Optional[str] = None, rwi_column: str = 'rwi') -> pd.DataFrame:
    """
   process relative wealth index (rwi) gpkg file (i.e 20XX-04-country-city_02-process-output_spatial_city_rwi.gpkg) into cleaned csv, rwi_area.csv format for visualization.

   uses standard deviation binning to show true wealth distribution.
    
    categories defined by standard deviations from the city mean:
    - least wealthy:  rwi < (mean - 1.0 * SD)
    - less wealthy:   (mean - 1.0 * SD) ≤ RWI < (mean - 0.5 * SD)
    - average wealth: (mean - 0.5 * SD) ≤ RWI < (mean + 0.5 * SD)
    - more wealthy:   (mean + 0.5 * SD) ≤ RWI < (mean + 1.0 * SD)
    - most wealthy:   rwi ≥ (mean + 1.0 * SD)
    
    Parameters:
    -----------
    input_gpkg_file : str
        Path to the input GeoPackage file (RWI grid data)
    output_file : str, optional
        Path for output CSV file. If None, saves to 'data/processed/rwi_area.csv'
    rwi_column : str, optional
        Name of the RWI column in the GeoPackage (default: 'rwi')
    
    Returns:
    --------
    pd.DataFrame
        Cleaned dataframe with columns: bin, count, percentage
    """
    
    try:
        # read gpkg file
        gdf = gpd.read_file(input_gpkg_file)
        
        # check if rwi column exists
        if rwi_column not in gdf.columns:
            raise ValueError(f"Column '{rwi_column}' not found in GeoPackage. Available columns: {list(gdf.columns)}")
        
        # remove any rows with "null" rwi values
        gdf_valid = gdf[gdf[rwi_column].notna()].copy()
        
        if len(gdf_valid) == 0:
            raise ValueError(f"No valid data found in '{rwi_column}' column")

        print(f"Original CRS: {gdf_valid.crs}")

        # reproject to appropriate projected crs for accurate area calculation
        if gdf_valid.crs and gdf_valid.crs.is_geographic:
            # estimate utm zone from centroid
            gdf_valid = gdf_valid.to_crs(gdf_valid.estimate_utm_crs())
            print(f"Reprojected to {gdf_valid.crs} for accurate area calculation")

        # calculate area for each grid cell (now in square meters)
        gdf_valid['area'] = gdf_valid.geometry.area

        print(f"\nRWI data range: {gdf_valid[rwi_column].min():.3f} to {gdf_valid[rwi_column].max():.3f}")
        print(f"Total grid cells: {len(gdf_valid):,}")
        print(f"Total area: {gdf_valid['area'].sum():,.0f} square meters")
    
    except Exception as e:
        raise Exception(f"Error reading GeoPackage file {input_gpkg_file}: {e}")
    
  # calculate mean and standard deviation (sd) of rwi values for specific city
    rwi_mean = gdf_valid[rwi_column].mean()
    rwi_sd = gdf_valid[rwi_column].std()
    
    print(f"\n{'='*60}")
    print(f"CITY STATISTICS (for Standard Deviation binning)")
    print(f"{'='*60}")
    print(f"Mean RWI:             {rwi_mean:.3f}")
    print(f"Standard Deviation:   {rwi_sd:.3f}")
    
    # define sd-based break points
    break_least_less = rwi_mean - 1.0 * rwi_sd  # -1.0 sd
    break_less_avg = rwi_mean - 0.5 * rwi_sd    # -0.5 sd
    break_avg_more = rwi_mean + 0.5 * rwi_sd    # +0.5 sd
    break_more_most = rwi_mean + 1.0 * rwi_sd   # +1.0 sd
    
    print(f"\nSTANDARD DEVIATION BREAK POINTS:")
    print(f"  Least wealthy boundary:   RWI < {break_least_less:.3f}  (mean - 1.0 SD)")
    print(f"  Less wealthy boundary:    {break_least_less:.3f} ≤ RWI < {break_less_avg:.3f}  (mean - 0.5 SD)")
    print(f"  Average wealth boundary:  {break_less_avg:.3f} ≤ RWI < {break_avg_more:.3f}  (mean ± 0.5 SD)")
    print(f"  More wealthy boundary:    {break_avg_more:.3f} ≤ RWI < {break_more_most:.3f}  (mean + 0.5 SD)")
    print(f"  Most wealthy boundary:    RWI ≥ {break_more_most:.3f}  (mean + 1.0 SD)")
    
    # create bins array for pd.cut
    bins = [
        -np.inf,
        break_least_less,
        break_less_avg,
        break_avg_more,
        break_more_most,
        np.inf
    ]
    
    labels = ['Least wealthy', 'Less wealthy', 'Average wealth', 'More wealthy', 'Most wealthy']
    
    # apply sd-based categorization
    gdf_valid['rwi_category'] = pd.cut(
        gdf_valid[rwi_column],
        bins=bins,
        labels=labels,
        include_lowest=True
    )
    
    # count grid cells and sum area for each rwi category
    bin_data = []
    total_area = gdf_valid['area'].sum()
    
    for category in labels:
        category_data = gdf_valid[gdf_valid['rwi_category'] == category]
        
        if len(category_data) > 0:
            count = len(category_data)
            area = category_data['area'].sum()
            percentage = (area / total_area) * 100
        else:
            count = 0
            area = 0
            percentage = 0.0
        
        bin_data.append({
            'bin': category,
            'count': int(count),
            'percentage': round(percentage, 2)
        })

    # create df
    result_df = pd.DataFrame(bin_data)

     # filter out categories with no data
    result_df = result_df[result_df['count'] > 0].copy()
    
    # check if there are fewer than 5 bins
    if len(result_df) < 5:
        print(f"\nNote: Only {len(result_df)} wealth categories created (expected 5)")
        print("This can happen if RWI values have many duplicates (especially with discrete vs continuous RWI values (e.g., 0, 1 vs. 0.0123, 0.943)) - Despite this, the percentages should always be correct because we're summing the actual grid cell areas - no data is discarded, just the bin boundaries might merge if needed.")
    
    # create output filename if not provided
    if output_file is None:
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/rwi_area.csv'
    
    # save cleaned data
    result_df.to_csv(output_file, index=False)
    
    # basic validation
    total_count = result_df['count'].sum()
    percentage_sum = result_df['percentage'].sum()
    
    print(f"\nCleaned RWI data saved to: {output_file}")
    print(f"Wealth categories: {len(result_df)}")
    print(f"Total grid cells analyzed: {total_count:,}")
    print(f"Percentage coverage verification: {percentage_sum:.1f}% (should be ~100%)")
    
    # show distribution
    print(f"\nWealth Distribution:")
    for idx, row in result_df.iterrows():
        print(f"- {row['bin']}: {row['count']} cells ({row['percentage']:.1f}%)")
    
    return result_df

# urban extent and change (cumulative kmˆ2 over time)
def clean_uba(input_file, output_file=None):
    """
    clean up the urban built area csv file (i.e., 20XX-0X-country-city_other_02-process-output_tabular_city_wsf_stats.csv) for visualization as uba.csv.
    
    parameters:
    -----------
    input_file : str
        Path to the input csv file
    output_file : str, optional
        Path for output.
    """
    
    # read the urban built area csv file
    df = pd.read_csv(input_file)
    
    # sort by year to ensure correct order
    df = df.sort_values('year').reset_index(drop=True)
    
    # create new df with desired structure
    result_df = pd.DataFrame({
        'year': range(1, len(df) + 1),  # sequential numbering starting from 1
        'yearName': df['year'],
        'uba': df['cumulative sq km'].round(2)  # round to 2 decimal places
    })
    
    # calculate urban built area growth percentage
    # growth percentage = ((current_year - previous_year) / previous_year) * 100
    result_df['growth_percentage'] = result_df['uba'].pct_change() * 100
    
    # round to 3 decimal places
    result_df['growth_percentage'] = result_df['growth_percentage'].round(3)
    
    # create output filename if not provided
    if output_file is None:
        import os
        # ensure the processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/uba.csv'
            
    # save the cleaned data
    result_df.to_csv(output_file, index=False)
    
    print(f"Cleaned data saved to: {output_file}")
    print(f"Years covered: {result_df['yearName'].min()} - {result_df['yearName'].max()}")
    print(f"Total data points: {len(result_df)}")
    print(f"UBA range: {result_df['uba'].min():.2f} - {result_df['uba'].max():.2f} sq km")
    
    return result_df

# urban extent and change (percentage area with different years of urban expansion, "Before 1985", "1986-1995", "1996-2005", and "2006-2015")
def clean_uba_area(input_tif_file: str, output_file: Optional[str] = None) -> pd.DataFrame:
    """
    process urban built-up area expansion tif file (i.e., city_wsf_evolution_projection.tif) into cleaned csv, uba_area.csv format for visualization.
    
    Parameters:
    -----------
    input_tif_file : str
        Path to the input TIF file
    output_file : str, optional
        Path for output CSV file. If None, saves to 'data/processed/uba_area.csv'
    
    Returns:
    --------
    pd.DataFrame
        Cleaned dataframe with columns: bin, year, count, percentage
    """
    
    try:
        # read tif file
        with rasterio.open(input_tif_file) as src:
            # read data as a numpy array
            uba_data = src.read(1)  # read first band
            
            # get valid data (exclude "NoData" values)
            nodata_value = src.nodata
            if nodata_value is not None:
                valid_data = uba_data[uba_data != nodata_value]
            else:
                # if no explicit "nodata" value, exclude "NaN" and very large/small values
                valid_data = uba_data[~np.isnan(uba_data)]
                valid_data = valid_data[np.isfinite(valid_data)]
            
            # filter out unrealistic year values (assuming reasonable range 1900-2030)
            valid_data = valid_data[(valid_data >= 1900) & (valid_data <= 2030)]
    
    except Exception as e:
        raise Exception(f"Error reading TIF file {input_tif_file}: {e}")
    
    # define bins for urban expansion years
    bins = [
        {"range": "Before 1985", "min_year": 0, "max_year": 1985},
        {"range": "1986-1995", "min_year": 1986, "max_year": 1995},
        {"range": "1996-2005", "min_year": 1996, "max_year": 2005},
        {"range": "2006-2015", "min_year": 2006, "max_year": 2015}
    ]
    
    # count pixels in each bin
    bin_data = []
    total_pixels = len(valid_data)
    
    for bin_info in bins:
        if bin_info["range"] == "Before 1985":
            # for "Before 1985" category, include all years <= 1985
            count = np.sum(valid_data <= bin_info["max_year"])
        else:
            # for specific ranges
            count = np.sum((valid_data >= bin_info["min_year"]) & (valid_data <= bin_info["max_year"]))
        
        # calculate representative year for the bin (midpoint or boundary)
        if bin_info["range"] == "Before 1985":
            representative_year = "≤1985"
        else:
            representative_year = f"{bin_info['min_year']}-{bin_info['max_year']}"
        
        bin_data.append({
            'bin': bin_info["range"],
            'year': representative_year,
            'count': int(count),
            'percentage': round((count / total_pixels) * 100, 2) if total_pixels > 0 else 0
        })
    
    # create df
    result_df = pd.DataFrame(bin_data)
    
    
    # create output filename if not provided
    if output_file is None:
        # ensure the processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/uba_area.csv'
    
    # save cleaned data
    result_df.to_csv(output_file, index=False)
    
    # basic validation
    total_count = result_df['count'].sum()
    percentage_sum = result_df['percentage'].sum()
    
    print(f"Cleaned UBA data saved to: {output_file}")
    print(f"Urban expansion periods: {len(result_df)}")
    print(f"Total pixels analyzed: {total_count:,.0f}")
    print(f"Percentage coverage verification: {percentage_sum:.1f}% (should be ~100%)")
    
    # ID dominant expansion period
    if len(result_df) > 0:
        dominant_bin = result_df.loc[result_df['percentage'].idxmax()]
        print(f"Dominant expansion period: {dominant_bin['bin']} ({dominant_bin['percentage']:.1f}%)")
    
    # show year range in data
    if len(valid_data) > 0:
        min_year = int(valid_data.min())
        max_year = int(valid_data.max())
        print(f"Year range in data: {min_year} - {max_year}")
    
    return result_df

# land cover
def clean_lc(input_file, output_file=None):
    """
    clean up the 20XX-02-country-city_02-process-output_tabular_city_lc.csv file for visualization as lc.csv.
    
    parameters:
    -----------
    input_file : str
        Path to the input csv file
    output_file : str, optional
        Path for output.
    """
    
    # read the land cover csv file
    df = pd.read_csv(input_file)
    
    # remove rows where "Pixel Count" is "0" (no coverage for that land type)
    # also remove any "total" or summary rows that might be in data
    df_filtered = df[
        (df['Pixel Count'] > 0) & 
        (~df['Land Cover Type'].str.contains('total', case=False, na=False))
    ].copy()
    
    # calculate total pixels for percentage calculation
    total_pixels = df_filtered['Pixel Count'].sum()
    
    # create new df with desired structure
    result_df = pd.DataFrame({
        'lcType': df_filtered['Land Cover Type'],
        'pixelCount': df_filtered['Pixel Count'].round(0).astype(int),
        'pixelTotal': total_pixels,
        'percentage': ((df_filtered['Pixel Count'] / total_pixels) * 100).round(2)
    })
    
    # sort by percentage in descending order (most common land cover first)
    result_df = result_df.sort_values('percentage', ascending=False).reset_index(drop=True)
    
    # create output filename if not provided
    if output_file is None:
        import os
        # ensure the processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/lc.csv'
            
    # save cleaned data
    result_df.to_csv(output_file, index=False)
    
    print(f"Cleaned data saved to: {output_file}")
    print(f"Land cover types: {len(result_df)}")
    print(f"Total pixels analyzed: {total_pixels:,.0f}")
    print(f"Percentage coverage verification: {result_df['percentage'].sum():.1f}% (should be ~100%)")
    
    # ID dominant land cover types
    dominant_type = result_df.iloc[0]
    print(f"Dominant land cover: {dominant_type['lcType']} ({dominant_type['percentage']:.1f}%)")
    
    return result_df

# population urban growth (urban development dynamics matrix)
def clean_pug(pg_file=None, uba_file=None, output_file=None):
    """
    clean up and merge population growth (pg.csv) and urban built area (uba.csv) csv files 
    for visualization as pug.csv (population urban growth ratio for urban development dynamics matrix).
    
    parameters:
    -----------
    pg_file : str, optional
        Path to the population growth CSV file (default: 'data/processed/pg.csv')
    uba_file : str, optional
        Path to the urban built area CSV file (default: 'data/processed/uba.csv')
    output_file : str, optional
        Path for output (default: 'data/processed/pug.csv')
    """
    
    # set default file paths if not provided
    if pg_file is None:
        pg_file = 'data/processed/pg.csv'
    if uba_file is None:
        uba_file = 'data/processed/uba.csv'
    
    # read pg.csv and uba.csv
    try:
        pg_df = pd.read_csv(pg_file)
        print(f"Successfully loaded population growth data: {len(pg_df)} records")
    except FileNotFoundError:
        raise FileNotFoundError(f"Population growth file not found: {pg_file}")
    except Exception as e:
        raise Exception(f"Error reading population growth file: {e}")
    
    try:
        uba_df = pd.read_csv(uba_file)
        print(f"Successfully loaded urban built area data: {len(uba_df)} records")
    except FileNotFoundError:
        raise FileNotFoundError(f"Urban built area file not found: {uba_file}")
    except Exception as e:
        raise Exception(f"Error reading urban built area file: {e}")
    
    # merge pg_df and uba_df on yearName to create pug
    pug_df = pd.merge(pg_df, uba_df, on='yearName', how='inner')
    print(f"Successfully merged datasets: {len(pug_df)} overlapping years")
    
    if len(pug_df) == 0:
        raise ValueError("No overlapping years found between population growth and urban built area data")
    
    # calculate density (population per unit area)
    pug_df['density'] = (pug_df['population'] / pug_df['uba']).round(3)
    
    # calculate population-urban growth percentage ratio
    # handle division by zero cases
    mask = pug_df['growth_percentage'] != 0
    pug_df['populationUrbanGrowthRatio'] = None
    pug_df.loc[mask, 'populationUrbanGrowthRatio'] = (
        pug_df.loc[mask, 'populationGrowthPercentage'] / 
        pug_df.loc[mask, 'growth_percentage']
    ).round(3)
    
    # reorder columns to match expected output structure
    expected_columns = ['yearName', 'population', 'populationGrowthPercentage', 'year', 'uba', 
                       'growth_percentage', 'density', 'populationUrbanGrowthRatio']
    
    # ensure all expected columns exist
    missing_columns = [col for col in expected_columns if col not in pug_df.columns]
    if missing_columns:
        print(f"⚠️  Warning: Missing expected columns: {missing_columns}")
    
    # reorder existing columns
    available_columns = [col for col in expected_columns if col in pug_df.columns]
    pug_df = pug_df[available_columns]
    
    # create output filename if not provided
    if output_file is None:
        import os
        # ensure the processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/pug.csv'
    
    # save pug_df for population urban growth data to csv
    pug_df.to_csv(output_file, index=False)
    
    print(f"Cleaned data saved to: {output_file}")
    print(f"Years covered: {pug_df['yearName'].min()} - {pug_df['yearName'].max()}")
    print(f"Total data points: {len(pug_df)}")
    print(f"Population range: {pug_df['population'].min():,} - {pug_df['population'].max():,}")
    print(f"UBA range: {pug_df['uba'].min():.2f} - {pug_df['uba'].max():.2f}")
    print(f"Density range: {pug_df['density'].min():.1f} - {pug_df['density'].max():.1f}")
    
    # check for any missing ratios
    missing_ratios = pug_df['populationUrbanGrowthRatio'].isna().sum()
    if missing_ratios > 0:
        print(f"Note: {missing_ratios} missing growth ratios (likely due to zero UBA growth)")
    
    return pug_df

# photovoltaic (monthly max pv potential)
def clean_pv(input_file, output_file=None):
    """
    clean up the monthly-pv.csv file for visualization as pv.csv.
    
    parameters:
    -----------
    input_file : str
        Path to the input csv file
    output_file : str, optional
        Path for output.
    """
    
    # read the monthly photovoltaic csv file
    df = pd.read_csv(input_file)
    
    # PV condition classification based on World Bank Global Solar Atlas standards
    # Reference: World Bank Global Photovoltaic Power Potential by Country study
    # https://www.worldbank.org/en/topic/energy/publication/solar-photovoltaic-power-potential-by-country
    def categorize_pv_condition(maxpv):
        """
        PV condition classification based on World Bank/Solargis Global Solar Atlas:
        - Excellent: >4.5 kWh/kWp
        - Favorable: 3.5-4.5 kWh/kWp
        - Less than Favorable: <3.5 kWh/kWp
        """
        if pd.isna(maxpv):
            return 'Unknown'
        elif maxpv > 4.5:
            return 'Excellent'
        elif maxpv >= 3.5:
            return 'Favorable'
        else:
            return 'Less than Favorable'
    
    # create new df with desired structure
    # extract max values for each month to create the simplified pv.csv structure
    result_df = pd.DataFrame({
        'month': df['month'],
        'monthName': df['month'].map({
            1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
            7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
        }),
        'maxPv': df['max'].round(2),  # round to 2 decimal places 
        'condition': df['max'].apply(categorize_pv_condition)
    })
    
    # sort by month to ensure proper order
    result_df = result_df.sort_values('month').reset_index(drop=True)
    
    # create output filename if not provided
    if output_file is None:
        import os
        # ensure the processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/pv.csv'
            
    # save cleaned data
    result_df.to_csv(output_file, index=False)
    
    print(f"Cleaned data saved to: {output_file}")
    print(f"Months covered: {len(result_df)} months (full year)")
    print(f"PV potential range: {result_df['maxPv'].min():.2f} - {result_df['maxPv'].max():.2f}")
    print(f"Peak month: {result_df.loc[result_df['maxPv'].idxmax(), 'monthName']} ({result_df['maxPv'].max():.2f})")
    print(f"Lowest month: {result_df.loc[result_df['maxPv'].idxmin(), 'monthName']} ({result_df['maxPv'].min():.2f})")
    
    # condition distribution (World Bank classification)
    condition_counts = result_df['condition'].value_counts()
    print(f"PV condition distribution (World Bank standards):")
    for condition in ['Excellent', 'Favorable', 'Less than Favorable']:
        count = condition_counts.get(condition, 0)
        print(f"  {condition}: {count} months")
    
    # calculate seasonal insights
    summer_months = result_df[result_df['month'].isin([6, 7, 8])]  # Jun, Jul, Aug
    winter_months = result_df[result_df['month'].isin([12, 1, 2])]  # Dec, Jan, Feb
    
    summer_avg = summer_months['maxPv'].mean()
    winter_avg = winter_months['maxPv'].mean()
    seasonal_variation = ((summer_avg - winter_avg) / winter_avg) * 100
    
    print(f"Summer average (Jun-Aug): {summer_avg:.2f}")
    print(f"Winter average (Dec-Feb): {winter_avg:.2f}")
    print(f"Seasonal variation: {seasonal_variation:.1f}% higher in summer")
    
    return result_df

# photovoltaic (% area with different pv conditions - "Excellent (4+5)","Favorable (3.5-4.5)","Less than Favorable (<3.5)")
def clean_pv_area(input_tif_file: str, output_file: Optional[str] = None) -> pd.DataFrame:
    """
    process photovoltaic potential tif file (i.e., solar.tif) into cleaned csv, pv_area.csv for visualization.
    
    Parameters:
    -----------
    input_tif_file : str
        Path to the input TIF file
    output_file : str, optional
        Path for output CSV file. If None, saves to 'data/processed/pv_area.csv'
    
    Returns:
    --------
    pd.DataFrame
        Cleaned dataframe with columns: bin, condition, count, percentage
    """
    
    try:
        # read tif file
        with rasterio.open(input_tif_file) as src:
            # read data as a numpy array
            pv_data = src.read(1)  # read first band
            
            # get valid data (exclude "NoData" values)
            nodata_value = src.nodata
            if nodata_value is not None:
                valid_data = pv_data[pv_data != nodata_value]
            else:
                # if no explicit, "NoData" value, exclude "NaN" and very large/small values
                valid_data = pv_data[~np.isnan(pv_data)]
                valid_data = valid_data[np.isfinite(valid_data)]
    
    except Exception as e:
        raise Exception(f"Error reading TIF file {input_tif_file}: {e}")
    
    # define bins and conditions based on photovoltaic potential values
    bins = [
        {"range": "<3.5", "condition": "Less than Favorable", "min_val": 0, "max_val": 3.5},
        {"range": "3.5-4.5", "condition": "Favorable", "min_val": 3.5, "max_val": 4.5},
        {"range": ">4.5", "condition": "Excellent", "min_val": 4.5, "max_val": float('inf')}
    ]
    
    # count pixels in each bin
    bin_data = []
    total_pixels = len(valid_data)
    
    for bin_info in bins:
        if bin_info["max_val"] == float('inf'):
            # for the "4.5+" (i.e., "Excellent") category
            count = np.sum(valid_data >= bin_info["min_val"])
        else:
            # for ranges with upper bounds
            count = np.sum((valid_data >= bin_info["min_val"]) & (valid_data < bin_info["max_val"]))
        
        bin_data.append({
            'bin': bin_info["range"],
            'condition': bin_info["condition"],
            'count': int(count),
            'percentage': round((count / total_pixels) * 100, 2) if total_pixels > 0 else 0
        })
    
    # create df
    result_df = pd.DataFrame(bin_data)
    
    # filter out bins with zero count
    # result_df = result_df[result_df['count'] > 0].copy()
    
    # create output filename if not provided
    if output_file is None:
        # ensure the "processed" directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/pv_area.csv'
    
    # save cleaned data
    result_df.to_csv(output_file, index=False)
    
    # basic validation
    total_count = result_df['count'].sum()
    percentage_sum = result_df['percentage'].sum()
    
    print(f"Cleaned PV data saved to: {output_file}")
    print(f"PV potential bins: {len(result_df)}")
    print(f"Total pixels analyzed: {total_count:,.0f}")
    print(f"Percentage coverage verification: {percentage_sum:.1f}% (should be ~100%)")
    
    # ID dominant condition
    if len(result_df) > 0:
        dominant_bin = result_df.loc[result_df['percentage'].idxmax()]
        print(f"Dominant PV condition: {dominant_bin['condition']} - {dominant_bin['bin']} ({dominant_bin['percentage']:.1f}%)")
    
    return result_df

# air quality (% area with different air quality conditions - i.e., PM2.5 particle concentrations in 2019 (µg/m³), [0-5), [5-10), [10-15), [15-20), [20-30), [30-40), [40-50), [50-100), [100+])
def clean_aq_area(input_tif_file: str, output_file: Optional[str] = None) -> pd.DataFrame:
    """
    process air quality tif file (i.e., 20XX-04-country-city_02-process-output_spatial_city_air.tif) into cleaned csv, aq_area.csv for visualization.
    
    Parameters:
    -----------
    input_tif_file : str
        Path to the input TIF file
    output_file : str, optional
        Path for output CSV file. If None, saves to 'data/processed/aq_area.csv'
    
    Returns:
    --------
    pd.DataFrame
        Cleaned dataframe with columns: bin, count, percentage
    """
    
    try:
        # read tif file
        with rasterio.open(input_tif_file) as src:
            # read data as numpy array
            pm25_data = src.read(1)  # read first band
            
            # get valid data (exclude "NoData" values)
            nodata_value = src.nodata
            if nodata_value is not None:
                valid_data = pm25_data[pm25_data != nodata_value]
            else:
                # if no explicit "nodata" value, exclude "NaN" and infinite values
                valid_data = pm25_data[~np.isnan(pm25_data)]
                valid_data = valid_data[np.isfinite(valid_data)]
            
            # remove negative values (i.e., shouldn't exist for PM2.5 concentrations)
            valid_data = valid_data[valid_data >= 0]
    
    except Exception as e:
        raise Exception(f"Error reading TIF file {input_tif_file}: {e}")
    
    # define PM2.5 concentration (μg/m³) bins using standard binning: [min_val, max_val) - inclusive lower, exclusive upper
    bins_definition = [
        {"range": "0-5", "min_val": 0, "max_val": 5},      # 0 ≤ value < 5
        {"range": "5-10", "min_val": 5, "max_val": 10},    # 5 ≤ value < 10
        {"range": "10-15", "min_val": 10, "max_val": 15},  # 10 ≤ value < 15
        {"range": "15-20", "min_val": 15, "max_val": 20},  # 15 ≤ value < 20
        {"range": "20-30", "min_val": 20, "max_val": 30},  # 20 ≤ value < 30
        {"range": "30-40", "min_val": 30, "max_val": 40},  # 30 ≤ value < 40
        {"range": "40-50", "min_val": 40, "max_val": 50},  # 40 ≤ value < 50
        {"range": "50-100", "min_val": 50, "max_val": 100}, # 50 ≤ value < 100
        {"range": "100+", "min_val": 100, "max_val": float('inf')} # value ≥ 100
    ]
    
    # show data range for validation
    if len(valid_data) > 0:
        print(f"PM2.5 data range: {valid_data.min():.2f} - {valid_data.max():.2f} μg/m³")
        print(f"Unique values in data: {len(np.unique(valid_data))}")
    
    # count pixels in each bin
    bin_data = []
    total_pixels = len(valid_data)
    
    for bin_info in bins_definition:
        if bin_info["max_val"] == float('inf'):
            # for the "100+" category
            count = np.sum(valid_data >= bin_info["min_val"])
        else:
            # for ranges with upper bounds
            # using inclusive lower bound, exclusive upper bound: [min_val, max_val)
            count = np.sum((valid_data >= bin_info["min_val"]) & (valid_data < bin_info["max_val"]))
        
        bin_data.append({
            'bin': bin_info["range"],
            'count': int(count),
            'percentage': round((count / total_pixels) * 100, 2) if total_pixels > 0 else 0
        })
    
    # create df
    result_df = pd.DataFrame(bin_data)
    
    # filter out bins with zero count
    # result_df = result_df[result_df['count'] > 0].copy()
    
    # create output filename if not provided
    if output_file is None:
        # ensure the processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/aq_area.csv'
    
    # save the cleaned data
    result_df.to_csv(output_file, index=False)
    
    # basic validation
    total_count = result_df['count'].sum()
    percentage_sum = result_df['percentage'].sum()
    
    print(f"Cleaned air quality data saved to: {output_file}")
    print(f"PM2.5 concentration bins: {len(result_df)}")
    print(f"Total pixels analyzed: {total_count:,.0f}")
    print(f"Percentage coverage verification: {percentage_sum:.1f}% (should be ~100%)")
    
    # ID dominant concentration range
    if len(result_df) > 0:
        # filter out zero-count categories for meaningful analysis
        active_categories = result_df[result_df['count'] > 0]
        if len(active_categories) > 0:
            dominant_category = active_categories.loc[active_categories['percentage'].idxmax()]
            print(f"Most common PM2.5 range: {dominant_category['bin']} μg/m³ ({dominant_category['percentage']:.1f}%)")
    
    return result_df

# summer surface temperature (% area with different summer surface temperatures)
def clean_summer_area(input_tif_file: str, output_file: Optional[str] = None, bin_width: int = 5) -> pd.DataFrame:
    """
    process summer surface temperature tif file (i.e., 20XX-04-country-city_02-process-output_spatial_city_summer.tif) in to cleaned csv, summer_area.csv for visualization.    
    
    Parameters:
    -----------
    input_tif_file : str
        Path to the input TIF file (summer surface temperature data in Celsius)
    output_file : str, optional
        Path for output CSV file. If None, saves to 'data/processed/summer_area.csv'
    bin_width : int, optional
        Width of temperature bins in degrees Celsius (default: 5)
    
    Returns:
    --------
    pd.DataFrame
        Cleaned dataframe with columns: bin, count, percentage
    """
    
    try:
        # read tif file
        with rasterio.open(input_tif_file) as src:
            # Read the data as a numpy array
            temp_data = src.read(1)  # Read first band
            
            # get valid data (exclude "NoData" values)
            nodata_value = src.nodata
            if nodata_value is not None:
                valid_data = temp_data[temp_data != nodata_value]
            else:
                # if no explicit "nodata" value, exclude "NaN" and infinite values
                valid_data = temp_data[~np.isnan(temp_data)]
                valid_data = valid_data[np.isfinite(valid_data)]
    
    except Exception as e:
        raise Exception(f"Error reading TIF file {input_tif_file}: {e}")
    
    # get temperature range
    min_temp = valid_data.min()
    max_temp = valid_data.max()
    
    print(f"Temperature data range: {min_temp:.1f}°C - {max_temp:.1f}°C")
    print(f"Total valid pixels: {len(valid_data):,}")
    
    # create dynamic bins based on data range
    # round min down to nearest bin_width, max up to nearest bin_width
    bin_start = int(np.floor(min_temp / bin_width) * bin_width)
    bin_end = int(np.ceil(max_temp / bin_width) * bin_width)
    
    # create bin edges
    bin_edges = list(range(bin_start, bin_end + bin_width, bin_width))
    
    print(f"Creating bins from {bin_start}°C to {bin_end}°C in {bin_width}°C increments")
    print(f"Number of bins: {len(bin_edges) - 1}")
    
    # count pixels in each bin
    bin_data = []
    total_pixels = len(valid_data)
    
    for i in range(len(bin_edges) - 1):
        lower = bin_edges[i]
        upper = bin_edges[i + 1]
        
        # for the last bin, include upper boundary (<=), otherwise exclude it (<)
        if i == len(bin_edges) - 2:
            count = np.sum((valid_data >= lower) & (valid_data <= upper))
        else:
            count = np.sum((valid_data >= lower) & (valid_data < upper))
        
        # create bin label
        bin_label = f"{lower}-{upper}"
        
        bin_data.append({
            'bin': bin_label,
            'count': int(count),
            'percentage': round((count / total_pixels) * 100, 2) if total_pixels > 0 else 0
        })
    
    # create df
    result_df = pd.DataFrame(bin_data)
    
    # filter out bins with zero count (optional - keeps empty bins for completeness)
    # result_df = result_df[result_df['count'] > 0].copy()
    
    # create output filename if not provided
    if output_file is None:
        # ensure processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/summer_area.csv'
    
    # save cleaned data
    result_df.to_csv(output_file, index=False)
    
    # basic validation and reporting
    total_count = result_df['count'].sum()
    percentage_sum = result_df['percentage'].sum()
    
    print(f"\nCleaned summer temperature data saved to: {output_file}")
    print(f"Temperature bins: {len(result_df)}")
    print(f"Total pixels analyzed: {total_count:,}")
    print(f"Percentage coverage verification: {percentage_sum:.1f}% (should be ~100%)")
    
    # ID dominant temperature range
    if len(result_df) > 0:
        # filter out zero-count bins for meaningful analysis
        active_bins = result_df[result_df['count'] > 0]
        if len(active_bins) > 0:
            dominant_bin = active_bins.loc[active_bins['percentage'].idxmax()]
            print(f"Most common temperature range: {dominant_bin['bin']}°C ({dominant_bin['percentage']:.1f}%)")
    
    return result_df

# green spaces, NDVI (% area with different NDVI - i.e., "Water", [-1-0.015); "Built-up", [0.015-0.14); "Barren", [0.14-0.18); "Shrub and Grassland", [0.18-0.27); "Sparse", [0.27-0.36); and "Dense",   [0.36-1])  
def clean_ndvi_area(input_tif_file: str, output_file: Optional[str] = None) -> pd.DataFrame:
    """
    process green space, NDVI tif file (i.e., 20XX-04-country-city_02-process-output_spatial_city_ndvi_season.tif) into cleaned csv, aq_area.csv for visualization.

    Parameters:
    -----------
    input_tif_file : str
        Path to the input TIF file
    output_file : str, optional
        Path for output CSV file. If None, saves to 'data/processed/ndvi_area.csv'
    
    Returns:
    --------
    pd.DataFrame
        Cleaned dataframe with columns: bin, type, count, percentage
    """
    
    try:
        # read tif file
        with rasterio.open(input_tif_file) as src:
            # read data as a numpy array
            ndvi_data = src.read(1)  # read first band
            
            # get valid data (exclude "NoData" values)
            nodata_value = src.nodata
            if nodata_value is not None:
                valid_data = ndvi_data[ndvi_data != nodata_value]
            else:
                # if no explicit "nodata" value, exclude "NaN" and infinite values
                valid_data = ndvi_data[~np.isnan(ndvi_data)]
            
            # remove infinite values from the valid_data (not the original array)
            valid_data = valid_data[np.isfinite(valid_data)]
    
    except Exception as e:
        raise Exception(f"Error reading TIF file {input_tif_file}: {e}")
    
    # define NDVI bins
    bins_definition = [
        {"range": "-1-0.015", "type": "Water", "min_val": -1.0, "max_val": 0.015},
        {"range": "0.015-0.14", "type": "Built-up", "min_val": 0.015, "max_val": 0.14},
        {"range": "0.14-0.18", "type": "Barren", "min_val": 0.14, "max_val": 0.18},
        {"range": "0.18-0.27", "type": "Shrub and Grassland", "min_val": 0.18, "max_val": 0.27},
        {"range": "0.27-0.36", "type": "Sparse", "min_val": 0.27, "max_val": 0.36},
        {"range": "0.36-1", "type": "Dense", "min_val": 0.36, "max_val": 1.0}
    ]
    
    # show data range for validation
    if len(valid_data) > 0:
        print(f"NDVI data range: {valid_data.min():.3f} - {valid_data.max():.3f}")
        print(f"Unique values in data: {len(np.unique(valid_data))}")
    
    # count pixels in each "bin"
    bin_data = []
    total_pixels = len(valid_data)
    
    for bin_info in bins_definition:
        if bin_info["range"] == "0.36-1":
            # for final "bin" [0.36-1], include the upper bound [inclusive]
            count = np.sum((valid_data >= bin_info["min_val"]) & (valid_data <= bin_info["max_val"]))
        else:
            # for other ranges, use [min_val, max_val) - [inclusive lower, exclusive upper)
            count = np.sum((valid_data >= bin_info["min_val"]) & (valid_data < bin_info["max_val"]))
        
        bin_data.append({
            'bin': bin_info["range"],
            'type': bin_info["type"],
            'count': int(count),
            'percentage': round((count / total_pixels) * 100, 2) if total_pixels > 0 else 0
        })
    
    # create df
    result_df = pd.DataFrame(bin_data)
    
    # create output filename if not provided
    if output_file is None:
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/ndvi_area.csv'
    
    # save the cleaned data
    result_df.to_csv(output_file, index=False)
    
    # basic validation
    total_count = result_df['count'].sum()
    percentage_sum = result_df['percentage'].sum()
    
    print(f"Cleaned NDVI data saved to: {output_file}")
    print(f"NDVI vegetation categories: {len(result_df)}")
    print(f"Total pixels analyzed: {total_count:,.0f}")
    print(f"Percentage coverage verification: {percentage_sum:.1f}% (should be ~100%)")
    
    return result_df


# forests and deforestation (% area with different forest cover and deforestation per year)  
def clean_deforestation_area(forest_tif_file: str, deforestation_tif_file: str, 
                             output_file: Optional[str] = None, 
                             base_year: int = 2000,
                             auto_align: bool = True) -> pd.DataFrame:
    """
    process forest cover (i.e., 20XX-04-country-city_02-process-output_spatial_city_forest_cover23.tif) and deforestation (i.e., 20XX-04-country-city_02-process-output_spatial_city_deforestation.tif) tif files into cleaned csv, deforestation_area.csv.
    
    Parameters:
    -----------
    forest_tif_file : str
        Path to forest cover TIF file (binary: 1=forest, 0/NoData=non-forest)
    deforestation_tif_file : str
        Path to deforestation TIF file (values 1-23 representing years since base_year)
    output_file : str, optional
        Path for output CSV. If None, saves to 'data/processed/deforestation_area.csv'
    base_year : int, optional
        Base year for deforestation data (default 2000, so value 1 = 2001)
    auto_align : bool, optional
        If True, automatically align/resample deforestation to match forest if misaligned
    
    Returns:
    --------
    pd.DataFrame
        Cleaned dataframe with columns: year, forest_remaining, deforested_this_year, 
        cumulative_deforested, percent_forest_remaining, percent_forest_lost
    """
    
    try:
        # read forest cover tif
        with rasterio.open(forest_tif_file) as forest_src:
            forest_data = forest_src.read(1)
            forest_nodata = forest_src.nodata
            forest_profile = forest_src.profile
            forest_transform = forest_src.transform
            forest_crs = forest_src.crs
            forest_bounds = forest_src.bounds
            forest_shape = forest_src.shape
            
        # read deforestation tif
        with rasterio.open(deforestation_tif_file) as deforest_src:
            deforest_data_original = deforest_src.read(1)
            deforest_nodata = deforest_src.nodata
            deforest_transform = deforest_src.transform
            deforest_crs = deforest_src.crs
            deforest_bounds = deforest_src.bounds
            deforest_shape = deforest_src.shape
            
        # check forest cover and deforestation alignment
        same_crs = forest_crs == deforest_crs
        same_shape = forest_shape == deforest_shape
        same_bounds = (abs(forest_bounds.left - deforest_bounds.left) < 1e-6 and
                      abs(forest_bounds.right - deforest_bounds.right) < 1e-6 and
                      abs(forest_bounds.top - deforest_bounds.top) < 1e-6 and
                      abs(forest_bounds.bottom - deforest_bounds.bottom) < 1e-6)
        same_transform = forest_transform == deforest_transform
        
        is_aligned = same_crs and same_shape and same_bounds and same_transform
        
        print(f"Alignment check:")
        print(f"- Same CRS: {same_crs}")
        print(f"- Same shape: {same_shape}")
        print(f"- Same bounds: {same_bounds}")
        print(f"- Fully aligned: {is_aligned}")
        
        if not is_aligned:
            if auto_align:
                print("\nAuto-aligning deforestation to match forest cover...")
                deforest_data = np.empty(forest_shape, dtype=deforest_data_original.dtype)
                reproject(
                    source=deforest_data_original,
                    destination=deforest_data,
                    src_transform=deforest_transform,
                    src_crs=deforest_crs,
                    src_nodata=deforest_nodata,
                    dst_transform=forest_transform,
                    dst_crs=forest_crs,
                    dst_nodata=deforest_nodata,
                    resampling=Resampling.nearest
                )
                print("Alignment complete")
            else:
                raise ValueError("TIF files are not aligned. Set auto_align=True to fix.")
        else:
            deforest_data = deforest_data_original
            print("TIFs are properly aligned")
        
        # use forest cover as primary mask
        if forest_nodata is not None:
            valid_mask = forest_data != forest_nodata
        else:
            valid_mask = ~np.isnan(forest_data) & np.isfinite(forest_data)
        
        forest_valid = forest_data[valid_mask]
        deforest_valid = deforest_data[valid_mask].copy()
        
        # treat "NoData" in deforestation as "0" (no deforestation)
        if deforest_nodata is not None:
            deforest_valid[deforest_valid == deforest_nodata] = 0
        deforest_valid[np.isnan(deforest_valid)] = 0
        
        # calculate baseline forest (only pixels where "value=1")
        baseline_forest = np.sum(forest_valid == 1)
        
        print(f"\nBaseline forest area: {baseline_forest:,} pixels")
        
    except Exception as e:
        raise Exception(f"Error reading TIF files: {e}")
    
    # build year-over-year data
    result_data = []
    
    # get unique deforestation years
    deforest_years = np.unique(deforest_valid[deforest_valid > 0])
    
    # add baseline year (no deforestation yet)
    result_data.append({
        'year': base_year,
        'forest_remaining': baseline_forest,
        'deforested_this_year': 0,
        'cumulative_deforested': 0,
        'percent_forest_remaining': 100.0,
        'percent_forest_lost': 0.0
    })
    
    # track cumulative deforestation
    cumulative_deforested = 0
    
    # add data for each year with deforestation
    for year_code in sorted(deforest_years):
        actual_year = base_year + int(year_code)
        
        # count pixels deforested this year (must be forest pixels)
        deforested_count = np.sum((forest_valid == 1) & (deforest_valid == year_code))
        cumulative_deforested += deforested_count
        
        forest_remaining = baseline_forest - cumulative_deforested
        percent_remaining = (forest_remaining / baseline_forest) * 100
        percent_lost = (cumulative_deforested / baseline_forest) * 100
        
        result_data.append({
            'year': actual_year,
            'forest_remaining': int(forest_remaining),
            'deforested_this_year': int(deforested_count),
            'cumulative_deforested': int(cumulative_deforested),
            'percent_forest_remaining': round(percent_remaining, 2),
            'percent_forest_lost': round(percent_lost, 2)
        })
    
    # create df
    result_df = pd.DataFrame(result_data)
    
    # create output filename if not provided
    if output_file is None:
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/deforestation_area.csv'
    
    # save cleaned data
    result_df.to_csv(output_file, index=False)
    
    # summary statistics
    final_year = result_df.iloc[-1]
    
    print(f"\nCleaned deforestation data saved to: {output_file}")
    print(f"Time period: {base_year} - {final_year['year']}")
    print(f"Baseline forest: {baseline_forest:,} pixels")
    print(f"Total deforested: {final_year['cumulative_deforested']:,} pixels ({final_year['percent_forest_lost']:.2f}%)")
    print(f"Forest remaining: {final_year['forest_remaining']:,} pixels ({final_year['percent_forest_remaining']:.2f}%)")
    
    # peak deforestation year
    peak_year = result_df[result_df['deforested_this_year'] > 0].loc[
        result_df['deforested_this_year'].idxmax()
    ]
    print(f"Peak deforestation year: {peak_year['year']} ({peak_year['deforested_this_year']:,} pixels)")
    
    return result_df
    
# flooding
def clean_flood(input_file, output_dir=None):
    """
    clean up the 20XX-0X-country-city_02-process-output_tabular_city_flood_wsf.csv file and create separate output csv files (i.e., fu.csv (fluvial), pu.csv (pluvial), cu.csv (coastal), and comb.csv (combined)) for each flood type based on available data in the input file.

    Note: flood-events.csv is not included as in input file because the csv is already cleaned and ready for visualization.
    
    parameters:
    -----------
    input_file : str
        Path to the input csv file
    output_dir : str, optional
        Directory for output files (default: 'data/processed/')
    """
    
    # read the flood data csv file
    df = pd.read_csv(input_file)
    
    # set default output directory
    if output_dir is None:
        import os
        output_dir = 'data/processed'
        os.makedirs(output_dir, exist_ok=True)
    
    # ID available flood types based on column names
    available_flood_types = {}
    
    # check for each flood type (looking for columns ending with _2020)
    if any('coastal_2020' in col for col in df.columns):
        available_flood_types['coastal'] = 'coastal_2020'
    if any('fluvial_2020' in col for col in df.columns):
        available_flood_types['fluvial'] = 'fluvial_2020'  
    if any('pluvial_2020' in col for col in df.columns):
        available_flood_types['pluvial'] = 'pluvial_2020'
    if any('comb_2020' in col for col in df.columns):
        available_flood_types['combined'] = 'comb_2020'
    
    print(f"Available flood types: {list(available_flood_types.keys())}")
    
    created_files = []
    
    # process each available flood type
    flood_mappings = {
        'fluvial': ('fu', 'fu.csv'),
        'pluvial': ('pu', 'pu.csv'), 
        'coastal': ('cu', 'cu.csv'),
        'combined': ('comb', 'comb.csv')
    }
    
    for flood_type, column_name in available_flood_types.items():
        if flood_type in flood_mappings:
            short_name, filename = flood_mappings[flood_type]
            
            # create df for flood type
            result_df = pd.DataFrame({
                'year': range(1, len(df) + 1),  # sequential numbering starting from 1
                'yearName': df['year'],  # actual year from input
                short_name: df[column_name].round(2)  # rounded flood values
            })
            
            # sort by year to ensure correct order
            result_df = result_df.sort_values('yearName').reset_index(drop=True)
            
            # save to csv
            output_path = os.path.join(output_dir, filename)
            result_df.to_csv(output_path, index=False)
            created_files.append(filename)
            
            print(f"Created {filename}: {len(result_df)} records")
            print(f"   Year range: {result_df['yearName'].min()} - {result_df['yearName'].max()}")
            print(f"   {short_name.upper()} range: {result_df[short_name].min():.2f} - {result_df[short_name].max():.2f}")
    
    # summary
    print(f"\nFlood Risk Data Processing Summary:")
    print(f"- Input file: {input_file}")
    print(f"- Output directory: {output_dir}")
    print(f"- Files created: {', '.join(created_files)}")
    print(f"- Missing flood types: {set(['fluvial', 'pluvial', 'coastal', 'combined']) - set(available_flood_types.keys())}")
    
    # data quality insights
    if len(available_flood_types) > 1:
        print(f"\nFlood Risk Analysis:")
        
        # compare flood types if multiple are available
        for flood_type, column_name in available_flood_types.items():
            avg_risk = df[column_name].mean()
            max_risk = df[column_name].max()
            min_risk = df[column_name].min()
            trend = df[column_name].iloc[-1] - df[column_name].iloc[0]  # latest - earliest
            
            print(f"- {flood_type.capitalize()} flood risk:")
            print(f"  Average: {avg_risk:.2f}, Range: {min_risk:.2f} - {max_risk:.2f}")
            print(f"  Trend (1985-2015): {trend:+.2f} ({'+increase' if trend > 0 else 'decrease' if trend < 0 else 'stable'})")
        
        # ID highest risk type
        latest_year_risks = {}
        for flood_type, column_name in available_flood_types.items():
            latest_year_risks[flood_type] = df[column_name].iloc[-1]
        
        highest_risk_type = max(latest_year_risks, key=latest_year_risks.get)
        print(f"- Dominant risk type (2015): {highest_risk_type.capitalize()} ({latest_year_risks[highest_risk_type]:.2f})")
    
    return created_files

# elevation
def clean_e(input_file, output_file=None):
    """
    clean up the elevation csv file (i.e., elevation.csv) for visualization as e.csv.
    
    parameters:
    -----------
    input_file : str
        Path to the input csv file
    output_file : str, optional
        Path for output.
    """
    
    # read the elevation csv file
    df = pd.read_csv(input_file)
    
    # remove any total/summary rows and zero-count rows
    df_filtered = df[
        (~df['Bin'].astype(str).str.contains('total', case=False, na=False)) &
        (df['Count'] > 0)
    ].copy()
    
    # sort elevation bins (handles different elevation ranges for different cities)
    def extract_elevation_value(bin_str):
        """Extract numeric value from elevation bin for sorting"""
        try:
            # negative elevations (e.g., "-45")
            if bin_str.startswith('-'):
                return float(bin_str)
            # range bins (e.g., "40-85", "130-175")
            elif '-' in bin_str:
                return float(bin_str.split('-')[0])
            # single values
            else:
                return float(bin_str)
        except (ValueError, AttributeError):
            # if parsing fails, return a very high number to put it at the end
            return 9999
    
    # add sorting column and sort by elevation
    df_filtered['sort_value'] = df_filtered['Bin'].apply(extract_elevation_value)
    df_filtered = df_filtered.sort_values('sort_value').reset_index(drop=True)
    
    # calculate total count for percentage calculation
    total_count = df_filtered['Count'].sum()
    
    # create new df with desired structure for Observable Plot
    result_df = pd.DataFrame({
        'bin': df_filtered['Bin'],
        'count': df_filtered['Count'].astype(int),
        'percentage': ((df_filtered['Count'] / total_count) * 100).round(2)
    })
    
    # create output filename if not provided
    if output_file is None:
        import os
        # ensure the processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/e.csv' 
            
    # save the cleaned data
    result_df.to_csv(output_file, index=False)
    
    print(f"Cleaned data saved to: {output_file}")
    print(f"Elevation bins: {len(result_df)}")
    print(f"Elevation range: {result_df['bin'].iloc[0]} to {result_df['bin'].iloc[-1]}")
    print(f"Total area analyzed: {total_count:,.0f} pixels")
    print(f"Percentage coverage verification: {result_df['percentage'].sum():.1f}% (should be ~100%)")
    
    # ID elevation distribution
    dominant_bin = result_df.loc[result_df['percentage'].idxmax()]
    print(f"Dominant elevation range: {dominant_bin['bin']} ({dominant_bin['percentage']:.1f}%)")
    
    # elevation range analysis (dynamic thresholds)
    major_bins = result_df[result_df['percentage'] >= 10]  # bins with ≥10% coverage
    if len(major_bins) > 0:
        print(f"Major elevation ranges (≥10% coverage): {len(major_bins)} bins")
        print(f"Major ranges: {', '.join(major_bins['bin'].tolist())}")
    
    return result_df

# slope
def clean_s(input_file, output_file=None):
    """
    clean up the slope csv file (i.e. city_slope.csv) for visualization as s.csv.

    parameters:
    -----------
    input_file : str
        Path to the input csv file
    output_file : str, optional
        Path for output.
    """
    
    # read the slope csv file
    df = pd.read_csv(input_file)
    
    # remove any total/summary rows and zero-count rows
    df_filtered = df[
        (~df['Bin'].astype(str).str.contains('total', case=False, na=False)) &
        (df['Count'] > 0)
    ].copy()
    
    # sort slope bins
    def extract_slope_value(bin_str):
        """Extract numeric value from slope bin for sorting"""
        try:
            # range bins (e.g., "0-2", "2-5", "5-10")
            if '-' in bin_str:
                return float(bin_str.split('-')[0])
            # single values
            else:
                return float(bin_str)
        except (ValueError, AttributeError):
            # if parsing fails, return a very high number to put it at the end
            return 9999
    
    # add sorting column and sort by slope
    df_filtered['sort_value'] = df_filtered['Bin'].apply(extract_slope_value)
    df_filtered = df_filtered.sort_values('sort_value').reset_index(drop=True)
    
    # calculate total count for percentage calculation
    total_count = df_filtered['Count'].sum()
    
    # create new df
    result_df = pd.DataFrame({
        'bin': df_filtered['Bin'],
        'count': df_filtered['Count'].astype(int),
        'percentage': ((df_filtered['Count'] / total_count) * 100).round(2)
    })
    
    # create output filename if not provided
    if output_file is None:
        import os
        # ensure the processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/s.csv'
            
    # save cleaned data
    result_df.to_csv(output_file, index=False)
    
    print(f"Cleaned data saved to: {output_file}")
    print(f"Slope bins: {len(result_df)}")
    print(f"Slope range: {result_df['bin'].iloc[0]} to {result_df['bin'].iloc[-1]} degrees")
    print(f"Total area analyzed: {total_count:,.0f} pixels")
    print(f"Percentage coverage verification: {result_df['percentage'].sum():.1f}% (should be ~100%)")
    
    # ID slope distribution
    dominant_bin = result_df.loc[result_df['percentage'].idxmax()]
    print(f"Dominant slope range: {dominant_bin['bin']} degrees ({dominant_bin['percentage']:.1f}%)")
    
    # slope range analysis
    flat_areas = result_df[result_df['bin'].str.contains('0-2|0-5', case=False, na=False)]
    if len(flat_areas) > 0:
        flat_percentage = flat_areas['percentage'].sum()
        print(f"Relatively flat areas (0-5 degrees): {flat_percentage:.1f}%")
    
    steep_areas = result_df[result_df['percentage'] >= 5]  # bins with ≥5% coverage
    if len(steep_areas) > 0:
        print(f"Significant slope ranges (≥5% coverage): {len(steep_areas)} bins")
        print(f"Significant ranges: {', '.join(steep_areas['bin'].tolist())}")
    
    return result_df

# landslide susceptibility (% area with different landslide susceptibility levels - "No Data" (0); "Very Low" (1); "Low" (2); "Medium" (3); "High" (4); "Very High" (5))

def clean_ls_area(input_tif_file: str, output_file: Optional[str] = None, include_nodata: bool = False) -> pd.DataFrame:
    """
    process landslide susceptibility tif file (/i.e., 20XX-04-country-city_02-process-output_spatial_city_landslide.tif) into cleaned csv, ls_area.csv for visualization.

    Parameters:
    -----------
    input_tif_file : str
        Path to the input TIF file
    output_file : str, optional
        Path for output CSV file. If None, saves to 'data/processed/ls_area.csv'
    include_nodata : bool, optional
        Whether to include value 0 (typically NoData) in the analysis. Default is False.
    
    Returns:
    --------
    pd.DataFrame
        Cleaned dataframe with columns: bin, susceptibility, count, percentage
    """
    
    try:
        # read tif file
        with rasterio.open(input_tif_file) as src:
            # read data as a numpy array
            landslide_data = src.read(1)  # read first band
            
            # get valid data (exclude "NoData" values if specified by rasterio)
            nodata_value = src.nodata
            if nodata_value is not None:
                valid_data = landslide_data[landslide_data != nodata_value]
            else:
                # if no explicit "NoData" value, exclude "NaN"
                valid_data = landslide_data[~np.isnan(landslide_data)]
                valid_data = valid_data[np.isfinite(valid_data)]
            
            # convert to integers for consistency
            valid_data = valid_data.astype(int)
            
            # filter data based on "include_nodata" parameter
            if not include_nodata:
                # exclude value, "0" ("NoData"/background)
                analysis_data = valid_data[valid_data > 0]
            else:
                analysis_data = valid_data
    
    except Exception as e:
        raise Exception(f"Error reading TIF file {input_tif_file}: {e}")
    
    # define landslide susceptibility mapping
    # note: ajusted to handle both scenarios (with/without value, "0")
    if include_nodata:
        susceptibility_mapping = {
            0: {"bin": "No Data", "label": "0"},
            1: {"bin": "Very low", "label": "1"},
            2: {"bin": "Low", "label": "2"},
            3: {"bin": "Medium", "label": "3"},
            4: {"bin": "High", "label": "4"},
            5: {"bin": "Very high", "label": "5"}
        }
    else:
        susceptibility_mapping = {
            1: {"bin": "Very low", "label": "1"},
            2: {"bin": "Low", "label": "2"},
            3: {"bin": "Medium", "label": "3"},
            4: {"bin": "High", "label": "4"},
            5: {"bin": "Very high", "label": "5"}
        }
    
    # count pixels for each landslide susceptibility level
    bin_data = []
    total_pixels = len(analysis_data)
    
    # get unique values in data
    unique_values = np.unique(analysis_data)
    print(f"Unique values found in data: {unique_values}")
    
    for value, mapping in susceptibility_mapping.items():
        if value in unique_values:
            count = np.sum(analysis_data == value)
        else:
            count = 0
        
        bin_data.append({
            'bin': mapping["bin"],
            'susceptibility': mapping["label"],
            'count': int(count),
            'percentage': round((count / total_pixels) * 100, 2) if total_pixels > 0 else 0
        })
    
    # create df
    result_df = pd.DataFrame(bin_data)
    
    # filter out bins with zero count
    # result_df = result_df[result_df['count'] > 0].copy()
    
    # sort by landslide susceptibility level (i.e., "Very low" to "Very high")
    susceptibility_order = ["No Data", "Very low", "Low", "Medium", "High", "Very high"]
    result_df['sort_order'] = result_df['bin'].map({cat: i for i, cat in enumerate(susceptibility_order)})
    result_df = result_df.sort_values('sort_order').drop('sort_order', axis=1).reset_index(drop=True)
    
    # create output filename if not provided
    if output_file is None:
        # ensure  processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/ls_area.csv'
    
    # save cleaned data
    result_df.to_csv(output_file, index=False)
    
    # basic validation
    total_count = result_df['count'].sum()
    percentage_sum = result_df['percentage'].sum()
    
    print(f"Cleaned landslide data saved to: {output_file}")
    print(f"Susceptibility categories: {len(result_df)}")
    print(f"Total pixels analyzed: {total_count:,.0f}")
    print(f"Percentage coverage verification: {percentage_sum:.1f}% (should be ~100%)")
    
    # ID dominant landslide susceptibility level
    if len(result_df) > 0:
        # filter out "zero-count" and "No Data" categories
        active_categories = result_df[(result_df['count'] > 0) & (result_df['bin'] != 'No Data')]
        if len(active_categories) > 0:
            dominant_category = active_categories.loc[active_categories['percentage'].idxmax()]
            print(f"Dominant susceptibility level: {dominant_category['bin']} ({dominant_category['percentage']:.1f}%)")
    
    return result_df

# earthquake events
def clean_ee(input_file, output_file=None):
    """
    clean up the earthquake-events.csv file for visualization as ee.csv.
    
    parameters:
    -----------
    input_file : str
        Path to the input csv file
    output_file : str, optional
        Path for output.
    """
    
    # read the earthquake events csv file
    df = pd.read_csv(input_file)
    
    # extract year from BEGAN column (format appears to be yyyy-mm-dd)
    df['begin_year'] = pd.to_datetime(df['BEGAN'], errors='coerce').dt.year
    
    # create new df with desired structure
    result_df = pd.DataFrame({
        'begin_year': df['begin_year'],
        'distance': df['distance'].round(0).astype('Int64'),  # round to whole numbers, handle "NaN"
        'eqMagnitude': df['eqMagnitude'].round(1),  # round to 1 decimal place
        'text': df['text'],
        'line1': df['line1'],
        'line2': df['line2'], 
        'line3': df['line3']
    })
    
    # remove rows with missing "begin_year" (invalid date parsing)
    result_df = result_df.dropna(subset=['begin_year'])
    
    # convert "begin_year" to integer
    result_df['begin_year'] = result_df['begin_year'].astype(int)
    
    # sort by year to ensure chronological order
    result_df = result_df.sort_values('begin_year').reset_index(drop=True)
    
    # create output filename if not provided
    if output_file is None:
        import os
        # ensure the processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/ee.csv'
            
    # save cleaned data
    result_df.to_csv(output_file, index=False)
    
    print(f"Cleaned data saved to: {output_file}")
    print(f"Earthquake events: {len(result_df)}")
    print(f"Year range: {result_df['begin_year'].min()} - {result_df['begin_year'].max()}")
    print(f"Magnitude range: {result_df['eqMagnitude'].min():.1f} - {result_df['eqMagnitude'].max():.1f}")
    print(f"Distance range: {result_df['distance'].min()} - {result_df['distance'].max()} km")
    
    return result_df

# liquefaction susceptibility (% area with different liquefaction susceptibility levels - "No Data" (0); "Very Low" (1); "Low" (2); "Medium" (3); "High" (4); "Very High" (5))

def clean_l_area(input_tif_file: str, output_file: Optional[str] = None, include_nodata: bool = False) -> pd.DataFrame:
    """
    process liquefaction susceptibility tif file (/i.e., 20XX-04-country-city_02-process-output_spatial_city_liquefaction.tif) into cleaned csv, l_area.csv for visualization.
    
    Parameters:
    -----------
    input_tif_file : str
        Path to the input TIF file
    output_file : str, optional
        Path for output CSV file. If None, saves to 'data/processed/l_area.csv'
    include_nodata : bool, optional
        Whether to include value 0 (typically NoData) in the analysis. Default is False.
    
    Returns:
    --------
    pd.DataFrame
        Cleaned dataframe with columns: bin, susceptibility, count, percentage
    """
    
    try:
        # read tif file
        with rasterio.open(input_tif_file) as src:
            # read data as a numpy array
            liquefaction_data = src.read(1)  # read first band
            
            # get valid data (exclude "NoData" values if specified by rasterio)
            nodata_value = src.nodata
            if nodata_value is not None:
                valid_data = liquefaction_data[liquefaction_data != nodata_value]
            else:
                # if no explicit "NoData" value, exclude "NaN"
                valid_data = liquefaction_data[~np.isnan(liquefaction_data)]
                valid_data = valid_data[np.isfinite(valid_data)]
            
            # convert to integers for consistent handling
            valid_data = valid_data.astype(int)
            
            # filter data based on "include_nodata" parameter
            if not include_nodata:
                # exclude value, "0" ("NoData"/background)
                analysis_data = valid_data[valid_data > 0]
            else:
                analysis_data = valid_data
    
    except Exception as e:
        raise Exception(f"Error reading TIF file {input_tif_file}: {e}")

    # define liquefaction susceptibility mapping
    # note: adjusted to handle both scenarios (with/without value 0)
    if include_nodata:
        susceptibility_mapping = {
            0: {"bin": "No Data", "label": "0"},
            1: {"bin": "Very low", "label": "1"},
            2: {"bin": "Low", "label": "2"},
            3: {"bin": "Medium", "label": "3"},
            4: {"bin": "High", "label": "4"},
            5: {"bin": "Very high", "label": "5"}
        }
    else:
        susceptibility_mapping = {
            1: {"bin": "Very low", "label": "1"},
            2: {"bin": "Low", "label": "2"},
            3: {"bin": "Medium", "label": "3"},
            4: {"bin": "High", "label": "4"},
            5: {"bin": "Very high", "label": "5"}
        }
    
    # count pixels for each liquefaction susceptibility level
    bin_data = []
    total_pixels = len(analysis_data)
    
    # get unique values in data
    unique_values = np.unique(analysis_data)
    print(f"Unique values found in data: {unique_values}")
    
    for value, mapping in susceptibility_mapping.items():
        if value in unique_values:
            count = np.sum(analysis_data == value)
        else:
            count = 0
        
        bin_data.append({
            'bin': mapping["bin"],
            'susceptibility': mapping["label"],
            'count': int(count),
            'percentage': round((count / total_pixels) * 100, 2) if total_pixels > 0 else 0
        })
    
    # create df
    result_df = pd.DataFrame(bin_data)
    
    # filter out bins with "zero count"
    # result_df = result_df[result_df['count'] > 0].copy()
    
    # sort by liquefaction susceptibility level ("Very low" to "Very high")
    susceptibility_order = ["No Data", "Very low", "Low", "Medium", "High", "Very high"]
    result_df['sort_order'] = result_df['bin'].map({cat: i for i, cat in enumerate(susceptibility_order)})
    result_df = result_df.sort_values('sort_order').drop('sort_order', axis=1).reset_index(drop=True)
    
    # create output filename if not provided
    if output_file is None:
        # ensure processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/l_area.csv'
    
    # save cleaned data
    result_df.to_csv(output_file, index=False)
    
    # basic validation
    total_count = result_df['count'].sum()
    percentage_sum = result_df['percentage'].sum()
    
    print(f"Cleaned liquefaction data saved to: {output_file}")
    print(f"Susceptibility categories: {len(result_df)}")
    print(f"Total pixels analyzed: {total_count:,.0f}")
    print(f"Percentage coverage verification: {percentage_sum:.1f}% (should be ~100%)")
    
    # ID dominant liquefaction susceptibility level
    if len(result_df) > 0:
        # filter out "zero-count" and "No Data" categories for meaningful analysis
        active_categories = result_df[(result_df['count'] > 0) & (result_df['bin'] != 'No Data')]
        if len(active_categories) > 0:
            dominant_category = active_categories.loc[active_categories['percentage'].idxmax()]
            print(f"Dominant susceptibility level: {dominant_category['bin']} ({dominant_category['percentage']:.1f}%)")
    
    return result_df

# fire weather index (fwi)
def clean_fwi(input_file, output_file=None):
    """
    clean up 20XX-02-country-city_02-process-output_tabular_city_fwi.csv file for visualization as fwi.csv.
    
    parameters:
    -----------
    input_file : str
        Path to the input csv file
    output_file : str, optional
        Path for output.
    """
    
    # read the fire weather index csv file
    df = pd.read_csv(input_file)
    
    # ISO 8601 standard week-to-month mapping
    # reference: ISO 8601:2004 Data elements and interchange formats
    # source: https://www.iso.org/standard/40874.html
    def get_month_name_iso(week):
        """ISO 8601 standard week-to-month mapping"""
        if week <= 4:
            return 'Jan'
        elif week <= 9:
            return 'Feb'  
        elif week <= 13:
            return 'Mar'
        elif week <= 17:
            return 'Apr'
        elif week <= 22:
            return 'May'
        elif week <= 26:
            return 'Jun'
        elif week <= 30:
            return 'Jul'
        elif week <= 35:
            return 'Aug'
        elif week <= 39:
            return 'Sep'
        elif week <= 43:
            return 'Oct'
        elif week <= 47:
            return 'Nov'
        else:  # weeks 48-53
            return 'Dec'
    
    # Fire Weather Index danger (i.e., risk) classification

    # source: https://climate-adapt.eea.europa.eu/en/metadata/indicators/fire-weather-index-monthly-mean-1979-2019
    def categorize_danger(fwi):
        """
        Fire Weather Index danger (i.e., risk) classification system
        Very low: < 5.2, Low: 5.2-11.2, Moderate: 11.2-21.3, 
        High: 21.3-38.0, Very high: 38.0-50.0, Extreme: > 50.0
        """
        if pd.isna(fwi):
            return 'Unknown'
        elif fwi < 5.2:
            return 'Very low'
        elif fwi < 11.2:
            return 'Low'
        elif fwi < 21.3:
            return 'Moderate'
        elif fwi < 38.0:
            return 'High'
        elif fwi < 50.0:
            return 'Very high'
        else:
            return 'Extreme'
    
    # create new df with desired structure
    result_df = pd.DataFrame({
        'week': df['week'],
        'monthName': df['week'].apply(get_month_name_iso),
        'fwi': df['pctile_95'].round(2),  # round to 2 decimal places
        'danger': df['pctile_95'].apply(categorize_danger)
    })
    
    # sort by week to ensure correct order
    result_df = result_df.sort_values('week').reset_index(drop=True)
    
    # create output filename if not provided
    if output_file is None:
        import os
        # ensure the processed directory exists
        os.makedirs('data/processed', exist_ok=True)
        output_file = 'data/processed/fwi.csv'
            
    # save cleaned data
    result_df.to_csv(output_file, index=False)
    
    print(f"Cleaned data saved to: {output_file}")
    print(f"Weeks covered: {len(result_df)} weeks")
    print(f"Week range: {result_df['week'].min()} - {result_df['week'].max()}")
    print(f"FWI range: {result_df['fwi'].min():.2f} - {result_df['fwi'].max():.2f}")
    
    # danger level distribution
    danger_counts = result_df['danger'].value_counts()
    print(f"Danger level distribution:")
    for level in ['Very low', 'Low', 'Moderate', 'High', 'Very high', 'Extreme']:
        count = danger_counts.get(level, 0)
        percentage = (count / len(result_df)) * 100
        print(f"  {level}: {count} weeks ({percentage:.1f}%)")
    
    # seasonal fire weather analysis using ISO standard
    seasonal_stats = result_df.groupby('monthName')['fwi'].agg(['mean', 'max']).round(2)
    peak_month = seasonal_stats['max'].idxmax()
    peak_fwi = seasonal_stats['max'].max()
    
    print(f"Peak fire weather month: {peak_month} (max FWI: {peak_fwi:.2f})")
    
    return result_df

# command line usage
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python clean.py input_file.csv [output_file.csv]")
        print("Available functions: clean_pg, clean_pas, clean_rwi_area, clean_uba, clean_uba_area, clean_lc, clean_pug, clean_pv, clean_pv_area, clean_aq_area, clean_summer_area, clean_ndvi_area, clean_deforestation_area, clean_flood, clean_e, clean_s, clean_ls_area, clean_ee, clean_l_area,clean_fwi")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    # determine which function to call based on filename or additional argument
    if 'population-growth' in input_file:
        clean_pg(input_file, output_file)
    elif 'demographics' in input_file:
        clean_pas(input_file, output_file)
    elif 'rwi' in input_file:
        clean_rwi_area(input_file, output_file)
    elif 'wsf_stats' in input_file: #wsft_stats, typo: fixed 15sept2025, 6:48 PM CEST
        clean_uba(input_file, output_file)
    elif 'wsf_evolution' in input_file:
        clean_uba_area(input_file, output_file)
    elif 'lc' in input_file:
        clean_lc(input_file, output_file)
    elif 'pug' in input_file:
        clean_pug(input_file, output_file)
    elif 'monthly-pv' in input_file:
        clean_pv(input_file, output_file)
    elif 'pv_area' in input_file:
        clean_pv_area(input_file, output_file)
    elif 'flood' in input_file:
        clean_flood(input_file, output_file)
    elif 'air' in input_file:
        clean_aq_area(input_file, output_file)
    elif 'ndvi' in input_file:
        clean_ndvi_area(input_file, output_file)
    elif 'summer' in input_file:
        clean_summer_area(input_file, output_file)
    elif 'forest' in input_file:
        clean_deforestation_area(input_file, output_file)
    elif 'deforestation' in input_file:
        clean_deforestation_area(input_file, output_file)
    elif 'elevation' in input_file:
        clean_e(input_file, output_file)
    elif 'slope' in input_file:
        clean_s(input_file, output_file)
    elif 'landslide' in input_file:
        clean_ls_area(input_file, output_file)
    elif 'earthquake-events' in input_file: 
        clean_ee(input_file, output_file)
    elif 'fwi' in input_file:
        clean_fwi(input_file, output_file)
    elif 'liquefaction' in input_file:
        clean_l_area(input_file, output_file)
    else:
        print("Cannot determine which cleaning function to use.")
        print("Please specify a file with 'population-growth' or 'demographics' or  'rwi' or 'wsf_stats' or 'wsf_evolution' or 'lc' or 'pug' or 'monthly-pv' or 'pv_area' or or 'air' or 'summer'or 'ndvi' or 'forest' or 'deforestation' or 'flood' or 'elevation' or 'slope' or 'landslide' or 'earthquake-events' or 'liquefaction' or 'fwi' in the name.")
        print(f"Your file: {input_file}")
        sys.exit(1)