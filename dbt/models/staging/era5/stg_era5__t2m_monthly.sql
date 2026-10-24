-- Monthly 2 m temperature per ERA5 grid point, in °C. One row per grid point and month.

with source as (

    select * from {{ source('era5', 'era5_t2m_monthly') }}

),

renamed as (

    select
        {{ grid_point_id('lat', 'lon') }}                  as grid_point_id,
        lat::double precision                              as lat,
        lon::double precision                              as lon,
        valid_month,
        extract(year from valid_month)::int                as year,
        extract(month from valid_month)::int               as month,
        {{ kelvin_to_celsius('t2m_k') }}::double precision as temp_c,
        expver,
        -- '0001' is final ERA5; other codes (e.g. '0005') are preliminary ERA5T
        coalesce(expver <> '0001', false)                  as is_preliminary,
        source_file,
        loaded_at

    from source

)

select * from renamed
