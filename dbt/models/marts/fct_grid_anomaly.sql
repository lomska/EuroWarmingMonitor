-- Each month's temperature compared with the grid point's climate normal
-- for that calendar month. Positive anomaly = warmer than normal.

with monthly as (

    select * from {{ ref('fct_grid_monthly_temp') }}

),

normals as (

    select * from {{ ref('fct_grid_normals') }}

)

select
    monthly.grid_point_id,
    monthly.valid_month,
    monthly.year,
    monthly.month,
    monthly.temp_c,
    normals.normal_c,
    monthly.temp_c - normals.normal_c   as anomaly_c,
    monthly.is_preliminary

from monthly
inner join normals
    on  normals.grid_point_id = monthly.grid_point_id
    and normals.month = monthly.month
