-- The annual normal must equal the day-weighted average of the 12 monthly
-- normals, within 0.02 °C (leap years make them differ very slightly).
-- Catches a wrong baseline filter or weighting in either table.

with monthly as (

    select
        grid_point_id,
        sum(normal_c * days) / sum(days) as normal_from_months_c
    from {{ ref('fct_grid_normals') }}
    cross join lateral (
        -- days per calendar month in a non-leap year
        select (array[31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])[month] as days
    ) as d
    group by grid_point_id

)

select
    annual.grid_point_id,
    annual.normal_c,
    monthly.normal_from_months_c
from {{ ref('fct_grid_annual_normals') }} as annual
inner join monthly
    on monthly.grid_point_id = annual.grid_point_id
where abs(annual.normal_c - monthly.normal_from_months_c) > 0.02
