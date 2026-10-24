-- The annual normal must equal the day-weighted average of the 12 monthly
-- normals, within 0.02 °C (leap years make them differ very slightly).
-- Catches a wrong baseline filter or weighting in either table.

with days_per_month as (

    -- days per calendar month in a non-leap year
    select
        days,
        month
    from unnest(array[31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
        with ordinality as d (days, month)

),

monthly as (

    select
        normals.grid_point_id,
        sum(normals.normal_c * days_per_month.days)
        / sum(days_per_month.days) as normal_from_months_c
    from {{ ref('fct_grid_normals') }} as normals
    inner join days_per_month
        on normals.month = days_per_month.month
    group by normals.grid_point_id

)

select
    annual.grid_point_id,
    annual.normal_c,
    monthly.normal_from_months_c
from {{ ref('fct_grid_annual_normals') }} as annual
inner join monthly
    on annual.grid_point_id = monthly.grid_point_id
where abs(annual.normal_c - monthly.normal_from_months_c) > 0.02
