-- Linear warming trend per grid point and calendar month over the whole record, °C per decade.

with monthly as (

    select * from {{ ref('fct_grid_monthly_temp') }}

)

select
    grid_point_id,
    month,
    regr_slope(temp_c, year) * 10 as warming_c_per_decade,
    regr_r2(temp_c, year)         as r_squared,
    count(*)                      as n_years,
    min(year)                     as first_year,
    max(year)                     as last_year

from monthly
group by 1, 2
