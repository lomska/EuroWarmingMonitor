-- The grid square (nearest grid point) of every place inside the study area.

{% set half = var('grid_step_deg') / 2 %}

with cities as (

    select * from {{ ref('stg_geonames__cities') }}

),

grid_points as (

    select * from {{ ref('int_grid_squares') }}

),

coverage as (

    -- The outer edges of the outermost squares
    select
        min(lat) - {{ half }} as south,
        max(lat) + {{ half }} as north,
        min(lon) - {{ half }} as west,
        max(lon) + {{ half }} as east
    from grid_points

),

cities_in_area as (

    select cities.*
    from cities
    cross join coverage
    where cities.lat between coverage.south and coverage.north
      and cities.lon between coverage.west and coverage.east

)

select
    cities_in_area.city_id,
    nearest.grid_point_id,
    nearest.distance_km

from cities_in_area
cross join lateral (
    select
        grid_points.grid_point_id,
        st_distance(
            grid_points.geom::geography,
            st_setsrid(st_makepoint(cities_in_area.lon, cities_in_area.lat), 4326)::geography
        ) / 1000 as distance_km
    from grid_points
    order by
        grid_points.geom <-> st_setsrid(st_makepoint(cities_in_area.lon, cities_in_area.lat), 4326),
        -- a place exactly on a border goes to the southern, then western, square
        grid_points.lat,
        grid_points.lon
    limit 1
) as nearest
