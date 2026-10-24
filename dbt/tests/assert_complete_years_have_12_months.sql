-- Fails for any grid point that is missing a month in a complete year
-- (every year except the latest, which may still be in progress).

with monthly as (

    select * from {{ ref('fct_grid_monthly_temp') }}

)

select
    grid_point_id,
    year,
    count(*) as months
from monthly
where year < (select max(latest.year) from monthly as latest)
group by grid_point_id, year
having count(*) <> 12
