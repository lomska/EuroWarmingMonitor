-- Land fraction per ERA5 grid point (0 = sea, 1 = land).

with source as (

    select * from {{ source('era5', 'era5_land_sea_mask') }}

),

renamed as (

    select
        {{ grid_point_id('lat', 'lon') }} as grid_point_id,
        lat::double precision             as lat,
        lon::double precision             as lon,
        lsm::double precision             as land_fraction

    from source

)

select * from renamed
