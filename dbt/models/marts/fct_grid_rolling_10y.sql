-- Rolling mean per grid point and calendar month over var('window_years'),
-- labelled by end year (January 1949 = Januaries 1940-1949).

with monthly as (

    select * from {{ ref('fct_grid_monthly_temp') }}

),

windowed as (

    select
        grid_point_id,
        month,
        year                                as window_end_year,
        avg(temp_c)             over w      as avg_temp_c,
        count(*)                over w      as years_in_window,
        min(year)               over w      as window_start_year,
        bool_or(is_preliminary) over w      as is_preliminary
    from monthly
    window w as (
        partition by grid_point_id, month
        order by year
        rows between {{ var('window_years') - 1 }} preceding and current row
    )

)

select
    grid_point_id,
    month,
    window_start_year,
    window_end_year,
    avg_temp_c,
    is_preliminary

from windowed
-- Complete windows only
where years_in_window = {{ var('window_years') }}
