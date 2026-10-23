-- Fails for any rolling window (monthly or annual) that does not cover exactly
-- var('window_years') years.

select 'monthly' as series, grid_point_id, window_start_year, window_end_year
from {{ ref('fct_grid_rolling_10y') }}
where window_end_year - window_start_year + 1 <> {{ var('window_years') }}

union all

select 'annual' as series, grid_point_id, window_start_year, window_end_year
from {{ ref('fct_grid_rolling_10y_annual') }}
where window_end_year - window_start_year + 1 <> {{ var('window_years') }}
