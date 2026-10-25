-- Every single year per grid point, for each calendar month (1-12) and the whole
-- year (0), with the rolling mean of the var('window_years') years ending then.
-- One table for the app's history chart: the line (rolling_avg_c) and the warming
-- stripes (temp_c). The rolling means come from the fct_grid_rolling_10y models,
-- so they are defined and tested in one place.
--
-- A view (set in the YAML): its rows already exist in the tables it joins, which
-- are indexed by grid point, and the app reads one grid point at a time.

with monthly as (

    select * from {{ ref('fct_grid_monthly_temp') }}

),

annual as (

    select * from {{ ref('fct_grid_annual_temp') }}

),

rolling_monthly as (

    select * from {{ ref('fct_grid_rolling_10y') }}

),

rolling_annual as (

    select * from {{ ref('fct_grid_rolling_10y_annual') }}

),

monthly_history as (

    select
        monthly.grid_point_id,
        monthly.month,
        monthly.year,
        monthly.temp_c,
        monthly.is_preliminary,
        rolling_monthly.window_start_year as rolling_start_year,
        rolling_monthly.avg_temp_c        as rolling_avg_c,
        rolling_monthly.is_preliminary    as rolling_is_preliminary
    from monthly
    -- The first years have no complete window yet: no rolling mean
    left join rolling_monthly
        on
            monthly.grid_point_id = rolling_monthly.grid_point_id
            and monthly.month = rolling_monthly.month
            and monthly.year = rolling_monthly.window_end_year

),

annual_history as (

    select
        annual.grid_point_id,
        0                                as month,
        annual.year,
        annual.temp_c,
        annual.is_preliminary,
        rolling_annual.window_start_year as rolling_start_year,
        rolling_annual.avg_temp_c        as rolling_avg_c,
        rolling_annual.is_preliminary    as rolling_is_preliminary
    from annual
    left join rolling_annual
        on
            annual.grid_point_id = rolling_annual.grid_point_id
            and annual.year = rolling_annual.window_end_year

),

combined as (

    select * from monthly_history
    union all
    select * from annual_history

)

select
    grid_point_id,
    month,
    year,
    temp_c,
    is_preliminary,
    rolling_start_year,
    rolling_avg_c,
    rolling_is_preliminary

from combined
