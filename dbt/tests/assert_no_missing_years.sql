-- Fails for any grid point with a gap in its years. The rolling window counts
-- rows, not years, so a missing year would silently widen a window.

select
    grid_point_id,
    min(year)            as first_year,
    max(year)            as last_year,
    count(distinct year) as years_present
from {{ ref('fct_grid_monthly_temp') }}
group by grid_point_id
having count(distinct year) <> max(year) - min(year) + 1
