-- The latest finished occurrence of each calendar month (1-12) and the latest
-- complete year (0) per grid square, compared with both climate normals and with
-- the same period a year earlier. Feeds the app's map and its key numbers.

with monthly as (

    select * from {{ ref('fct_grid_monthly_temp') }}

),

annual as (

    select * from {{ ref('fct_grid_annual_temp') }}

),

monthly_normals as (

    select * from {{ ref('fct_grid_normals') }}

),

annual_normals as (

    select * from {{ ref('fct_grid_annual_normals') }}

),

-- e.g. in October 2026: September 2026, but October 2025
latest_month as (

    select
        month,
        max(year) as year
    from monthly
    group by month

),

monthly_latest as (

    select
        monthly.grid_point_id,
        monthly.month,
        monthly.year,
        monthly.temp_c,
        monthly.is_preliminary,
        previous.temp_c as previous_year_temp_c,
        monthly_normals.normal_c,
        monthly_normals.early_normal_c
    from monthly
    inner join latest_month
        on
            monthly.month = latest_month.month
            and monthly.year = latest_month.year
    inner join monthly_normals
        on
            monthly.grid_point_id = monthly_normals.grid_point_id
            and monthly.month = monthly_normals.month
    left join monthly as previous
        on
            monthly.grid_point_id = previous.grid_point_id
            and previous.valid_month = (monthly.valid_month - interval '1 year')::date

),

annual_latest as (

    select
        annual.grid_point_id,
        0               as month,
        annual.year,
        annual.temp_c,
        annual.is_preliminary,
        previous.temp_c as previous_year_temp_c,
        annual_normals.normal_c,
        annual_normals.early_normal_c
    from annual
    inner join annual_normals
        on annual.grid_point_id = annual_normals.grid_point_id
    left join annual as previous
        on
            annual.grid_point_id = previous.grid_point_id
            and previous.year = annual.year - 1
    where annual.year = (select max(latest.year) from annual as latest)

),

combined as (

    select * from monthly_latest
    union all
    select * from annual_latest

)

select
    grid_point_id,
    month,
    year,
    temp_c,
    normal_c,
    early_normal_c,
    previous_year_temp_c,
    temp_c - normal_c             as change_vs_normal_c,
    temp_c - early_normal_c       as change_vs_early_normal_c,
    temp_c - previous_year_temp_c as change_vs_previous_year_c,
    is_preliminary

from combined
