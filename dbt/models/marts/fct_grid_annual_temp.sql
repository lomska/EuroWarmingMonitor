-- Annual mean temperature per grid point, complete years only.
-- Months are weighted by their number of days (leap years included).

with monthly as (

    select
        *,
        extract(day from (valid_month + interval '1 month' - interval '1 day'))::int
            as days_in_month
    from {{ ref('fct_grid_monthly_temp') }}

)

select
    grid_point_id,
    year,
    sum(temp_c * days_in_month) / sum(days_in_month) as temp_c,
    bool_or(is_preliminary)                          as is_preliminary

from monthly
group by grid_point_id, year
having count(*) = 12
