-- Linear warming trend of annual mean temperature per grid point, °C per decade.

with annual as (

    select * from {{ ref('fct_grid_annual_temp') }}

)

select
    grid_point_id,
    regr_slope(temp_c, year) * 10 as warming_c_per_decade,
    regr_r2(temp_c, year)         as r_squared,
    count(*)                      as n_years,
    min(year)                     as first_year,
    max(year)                     as last_year

from annual
group by grid_point_id
