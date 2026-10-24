-- Monthly mean 2 m temperature per grid point, in °C.
-- Incremental: processes only rows loaded since the last run. Rebuild with
-- --full-refresh after changing this model's columns or logic.

{{
    config(
        materialized='incremental',
        unique_key=['grid_point_id', 'valid_month'],
        incremental_strategy='delete+insert',
        on_schema_change='fail'
    )
}}

with temperatures as (

    select * from {{ ref('stg_era5__t2m_monthly') }}

    {% if is_incremental() %}
        where loaded_at > (select max(existing.source_loaded_at) from {{ this }} as existing)
    {% endif %}

)

select
    grid_point_id,
    valid_month,
    year,
    month,
    temp_c,
    is_preliminary,
    loaded_at as source_loaded_at

from temperatures
