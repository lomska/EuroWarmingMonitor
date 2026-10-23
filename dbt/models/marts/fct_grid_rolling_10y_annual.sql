-- Rolling mean of annual temperatures per grid point over var('window_years'),
-- labelled by end year (1949 = years 1940-1949).

with annual as (

    select * from {{ ref('fct_grid_annual_temp') }}

),

windowed as (

    select
        grid_point_id,
        year                                as window_end_year,
        avg(temp_c)             over w      as avg_temp_c,
        count(*)                over w      as years_in_window,
        min(year)               over w      as window_start_year,
        bool_or(is_preliminary) over w      as is_preliminary
    from annual
    window w as (
        partition by grid_point_id
        order by year
        rows between {{ var('window_years') - 1 }} preceding and current row
    )

)

select
    grid_point_id,
    window_start_year,
    window_end_year,
    avg_temp_c,
    is_preliminary

from windowed
-- Complete windows only
where years_in_window = {{ var('window_years') }}
