"""Demographic projection and charting functions for city and country population structures."""
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import logging
LOGGER = logging.getLogger('city_pipeline')

def _quiet_print(*args, level: str='debug') -> None:
    """Route legacy print-style messages through the pipeline logger."""
    message = ' '.join((str(arg) for arg in args))
    getattr(LOGGER, level, LOGGER.debug)(message)

def demographic_projection(city, country_iso3, country, ssp_to_use, section, data):
    """Project city and country demographic structure under the requested SSP scenario."""
    gc_city_folder = os.path.join(data, f'{section[0]}/GC_countries/')
    ssp_master_fn = os.path.join(data, f'{section[0]}/SspDb_country_data_2013-06-12.csv')
    ssp_master = pd.read_csv(ssp_master_fn)
    ssp_country = ssp_master.loc[ssp_master['REGION'] == country_iso3]
    ssp_country.reset_index(inplace=True, drop=True)
    if len(ssp_country) == 0:
        _quiet_print('Country not found in SSP database. Check if ISO3 name of the country is correct, and whether the country is actually available in the SSP database.', level='warning')
        return (0, 0)
    else:
        del ssp_master
    global_cities = pd.read_csv(gc_city_folder + 'GC_{}.csv'.format(country_iso3))
    gc_city = global_cities.loc[global_cities['Location'] == city]
    if len(gc_city) == 0:
        _quiet_print('City not found in the Global Cities database. Manually check if the city name spelling is correct, and whether the city is actually available in the Global Cities database.', level='warning')
        return (0, 0)
    else:
        del global_cities
    all_variables = list(np.unique(ssp_country['VARIABLE']))
    all_age_variables = [x for x in all_variables if 'Aged' in x]
    children_ssp = ['Aged0-4', 'Aged5-9', 'Aged10-14']
    young_adult_ssp = ['Aged15-19', 'Aged20-24', 'Aged25-29', 'Aged30-34']
    adult_ssp = ['Aged35-39', 'Aged40-44', 'Aged45-49', 'Aged50-54', 'Aged55-59', 'Aged60-64']
    elderly_ssp = ['Aged65-69', 'Aged70-74', 'Aged75-79', 'Aged80-84', 'Aged85-89', 'Aged90-94', 'Aged95-99', 'Aged100+']
    buckets_ssp = {'children': children_ssp, 'young_adult': young_adult_ssp, 'adult': adult_ssp, 'elderly': elderly_ssp}

    def get_population_ssp_year(ssp_country, ssp, year, buckets_ssp, all_variables):
        """Aggregate SSP age-group values for a single year and scenario."""
        age_groups = []
        population = []
        for age_group in buckets_ssp.keys():
            filtered_vars = list(filter(lambda x: np.sum([y in x for y in buckets_ssp[age_group]]) > 0, all_variables))
            filtered_vars = [x for x in filtered_vars if len(x.split('|')) == 3]
            filtered_dataframe = ssp_country.loc[ssp_country['VARIABLE'].isin(filtered_vars)]
            filtered_dataframe = filtered_dataframe.loc[filtered_dataframe['SCENARIO'].str.contains(ssp)]
            age_groups.append(age_group)
            try:
                population.append(filtered_dataframe[year].sum())
            except Exception:
                population.append(filtered_dataframe[str(year)].sum())
        output = pd.DataFrame()
        output['age_group'] = age_groups
        output['population'] = population
        output['ssp'] = ssp
        output['year'] = year
        return output
    pop_2010_sspA = get_population_ssp_year(ssp_country, ssp_to_use, 2010, buckets_ssp, all_variables)
    pop_2020_sspA = get_population_ssp_year(ssp_country, ssp_to_use, 2020, buckets_ssp, all_variables)
    hstr_chg_country = {}
    for age_group in buckets_ssp.keys():
        pop_2020 = pop_2020_sspA.loc[pop_2020_sspA['age_group'] == age_group, 'population'].values[0]
        pop_2010 = pop_2010_sspA.loc[pop_2010_sspA['age_group'] == age_group, 'population'].values[0]
        hstr_chg_country[age_group] = (pop_2020 - pop_2010) / pop_2010
    gc_city_slc = gc_city.loc[gc_city['Year'].isin([2010, 2020])]
    children_gc = ['POP0_14T']
    young_adult_gc = ['POP15_19T', 'POP20_24T', 'POP25_29T', 'POP30_34T']
    adult_gc = ['POP35_39T', 'POP40_44T', 'POP45_49T', 'POP50_54T', 'POP55_59T', 'POP60_64T']
    elderly_gc = ['POP65_T']
    buckets_gc = {'children': children_gc, 'young_adult': young_adult_gc, 'adult': adult_gc, 'elderly': elderly_gc}
    hstr_chg_city = {}
    for age_group in buckets_gc.keys():
        pop_2020 = gc_city_slc.loc[gc_city_slc['Year'] == 2020][buckets_gc[age_group]].sum().values[0]
        pop_2010 = gc_city_slc.loc[gc_city_slc['Year'] == 2010][buckets_gc[age_group]].sum().values[0]
        hstr_chg_city[age_group] = (pop_2020 - pop_2010) / pop_2010
    scaling_factor = {}
    for age_group in buckets_gc.keys():
        scaling_factor[age_group] = hstr_chg_city[age_group] / hstr_chg_country[age_group]
    country_pop = pd.DataFrame(columns=['Year'] + list(buckets_gc.keys()))
    city_pop = pd.DataFrame()
    city_pop['Year'] = [2020]
    for age_group in buckets_gc.keys():
        city_pop[age_group] = [gc_city_slc.loc[gc_city_slc['Year'] == 2020][buckets_gc[age_group]].sum().values[0]]
    for i in np.arange(2025, 2105, 5):
        pop_future1_sspA = get_population_ssp_year(ssp_country, ssp_to_use, i - 5, buckets_ssp, all_variables)
        pop_future2_sspA = get_population_ssp_year(ssp_country, ssp_to_use, i, buckets_ssp, all_variables)
        future_chg_country = {}
        for age_group in buckets_ssp.keys():
            pop_future1 = pop_future1_sspA.loc[pop_future1_sspA['age_group'] == age_group, 'population'].values[0]
            pop_future2 = pop_future2_sspA.loc[pop_future2_sspA['age_group'] == age_group, 'population'].values[0]
            future_chg_country[age_group] = (pop_future2 - pop_future1) / pop_future1
        future_chg_city = {}
        for age_group in buckets_ssp.keys():
            future_chg_city[age_group] = future_chg_country[age_group] * scaling_factor[age_group]
        to_input = []
        to_input.append(i)
        for age_group in buckets_gc.keys():
            current_pop = city_pop.loc[city_pop['Year'] == i - 5, age_group].values[0]
            future_pop = current_pop + current_pop * future_chg_city[age_group]
            to_input.append(future_pop)
        city_pop.loc[len(city_pop)] = to_input
        if i == 2025:
            country_pop.loc[len(country_pop)] = [i - 5] + [pop_future1_sspA.loc[pop_future1_sspA['age_group'] == list(buckets_gc.keys())[j]]['population'].values[0] for j in range(len(list(buckets_gc.keys())))]
        country_pop.loc[len(country_pop)] = [i] + [pop_future2_sspA.loc[pop_future2_sspA['age_group'] == list(buckets_gc.keys())[j]]['population'].values[0] for j in range(len(list(buckets_gc.keys())))]
    city_pop['SSP'] = ssp_to_use
    country_pop['SSP'] = ssp_to_use
    return (city_pop, country_pop)

def pyramid(city_pop, year1, year2, ssp, section, maps, city, country):
    """Create a demographic pyramid comparing two years for a selected SSP scenario."""
    city_pop_pyramid = city_pop.loc[city_pop['Year'].isin([year1, year2])]
    city_pop_pyramid = city_pop_pyramid.loc[city_pop_pyramid['SSP'] == ssp]
    city_pop_pyramid = city_pop_pyramid[city_pop_pyramid.columns[1:-1]]
    city_pop_pyramid = city_pop_pyramid.div(city_pop_pyramid.sum(axis=1), axis=0)
    city_pop_pyramid *= 100
    city_pop_pyramid['Year'] = [year1, year2]
    arr1 = city_pop_pyramid.loc[city_pop_pyramid['Year'] == year1].values[0][:-1]
    arr1 *= -1
    arr2 = city_pop_pyramid.loc[city_pop_pyramid['Year'] == year2].values[0][:-1]
    minval = np.floor(np.min(arr1) / 20)
    maxval = np.ceil(np.max(arr2) / 20)
    topper = np.max([np.abs(minval), np.abs(maxval)])
    fig_sns, ax_sns = plt.subplots(figsize=(7, 5))
    ax_sns = sns.barplot(x=arr1, y=city_pop_pyramid.columns[:-1], color='blue', ax=ax_sns)
    ax_sns = sns.barplot(x=arr2, y=city_pop_pyramid.columns[:-1], color='green', ax=ax_sns)
    plt.xticks(ticks=[-topper * 20, -topper * 10, 0, topper * 10, topper * 20], labels=['{}%'.format(topper * 20), '{}%'.format(topper * 10), '0', '{}%'.format(topper * 10), '{}%'.format(topper * 20)])
    ax_sns.text(x=0.25, y=1.05, s=year1, transform=ax_sns.transAxes, horizontalalignment='center', fontsize=12, color='blue')
    ax_sns.text(x=0.75, y=1.05, s=year2, transform=ax_sns.transAxes, horizontalalignment='center', fontsize=12, color='green')
    ax_sns.text(x=0.5, y=1.08, s=ssp, transform=ax_sns.transAxes, horizontalalignment='center', fontsize=15, color='black')
    ax_sns.axvline(color='white')
    ax_sns.figure.savefig(f'{maps}/{country}_{city}_{section[0]}_{ssp}_{year1}_{year2}_pyramid.jpeg', dpi=300, bbox_inches='tight')
    plt.close(ax_sns.figure)

def pop_lineplot(city_pop, ssp, section, maps, city, country):
    """Create a demographic line chart for the projected city population groups."""
    city_pop_ = city_pop.loc[city_pop['SSP'] == ssp]
    fig, ax = plt.subplots()
    sns.lineplot(x='Year', y='children', data=city_pop_, color='#1b9e77', ax=ax)
    sns.lineplot(x='Year', y='young_adult', data=city_pop_, color='#d95f02', ax=ax)
    sns.lineplot(x='Year', y='adult', data=city_pop_, color='#7570b3', ax=ax)
    sns.lineplot(x='Year', y='elderly', data=city_pop_, color='#e7298a', ax=ax)
    ax.legend(['Children', 'Young adult', 'Adult', 'Elderly'], loc='upper left', bbox_to_anchor=(0.98, 1))
    ax.set_ylabel("Population ('000)")
    ax.set_title('{} - {}'.format(city, ssp), fontsize=14)
    sns.despine()
    ax.figure.savefig(f'{maps}/{country}_{city}_{section[0]}_{ssp}_lineplot.jpeg', dpi=300, bbox_inches='tight')
    plt.close(ax.figure)
