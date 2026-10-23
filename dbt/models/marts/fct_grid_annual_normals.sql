-- Annual climate normals per grid point for the two baselines in vars, and the change.

with annual as (

    select * from {{ ref('fct_grid_annual_temp') }}

)

select
    grid_point_id,
    avg(temp_c) filter (
        where year between {{ var('baseline_start') }} and {{ var('baseline_end') }}
    )                                                   as normal_c,
    avg(temp_c) filter (
        where year between {{ var('early_baseline_start') }} and {{ var('early_baseline_end') }}
    )                                                   as early_normal_c,
    avg(temp_c) filter (
        where year between {{ var('baseline_start') }} and {{ var('baseline_end') }}
    )
    - avg(temp_c) filter (
        where year between {{ var('early_baseline_start') }} and {{ var('early_baseline_end') }}
    )                                                   as change_c

from annual
group by grid_point_id
