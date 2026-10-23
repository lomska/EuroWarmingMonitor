-- Fails for any rolling window that does not cover exactly var('window_years') years.

select *
from {{ ref('fct_grid_rolling_10y') }}
where window_end_year - window_start_year + 1 <> {{ var('window_years') }}
