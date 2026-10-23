-- One row per ERA5 grid point and the square it represents (the point is its centre).

{% set half = var('grid_step_deg') / 2 %}

with grid_points as (

    select * from {{ ref('stg_era5__land_sea_mask') }}

),

shaped as (

    select
        grid_point_id,
        lat,
        lon,
        land_fraction,
        land_fraction >= 0.5                          as is_land,
        st_setsrid(st_makepoint(lon, lat), 4326)      as geom,
        st_makeenvelope(
            lon - {{ half }}, lat - {{ half }},
            lon + {{ half }}, lat + {{ half }},
            4326
        )                                             as square
    from grid_points

)

select
    *,
    st_area(square::geography) / 1e6                  as area_km2

from shaped
