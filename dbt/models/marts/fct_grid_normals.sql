-- Normals per grid point and calendar month for the two baselines in vars, and the change.

with monthly as (

    select * from {{ ref('fct_grid_monthly_temp') }}

)

select
    grid_point_id,
    month,
    avg(temp_c) filter (
        where year between {{ var('baseline_start') }} and {{ var('baseline_end') }}
    ) as normal_c,
    avg(temp_c) filter (
        where year between {{ var('early_baseline_start') }} and {{ var('early_baseline_end') }}
    ) as early_normal_c,
    avg(temp_c) filter (
        where year between {{ var('baseline_start') }} and {{ var('baseline_end') }}
    )
    - avg(temp_c) filter (
        where year between {{ var('early_baseline_start') }} and {{ var('early_baseline_end') }}
    ) as change_c

from monthly
group by 1, 2
