-- The grid square (nearest grid point) of every place inside the study area.

{% set half = var('grid_step_deg') / 2 %}

with cities as (

    select * from {{ ref('stg_geonames__cities') }}

),

-- not materialized: grid_points is used twice, and a materialized CTE would
-- copy the rows without their spatial index, so the search would scan them all
grid_points as not materialized (

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
    -- The 4 nearest grid points come from the spatial index (ORDER BY distance
    -- only). A place ties with at most 4 points (on a corner), so re-sorting
    -- these 4 with the tie-breaker gives the same answer as sorting them all.
    select
        nearest_four.grid_point_id,
        st_distance(
            nearest_four.geom::geography,
            st_setsrid(st_makepoint(cities_in_area.lon, cities_in_area.lat), 4326)::geography
        ) / 1000 as distance_km
    from (
        select
            grid_points.grid_point_id,
            grid_points.lat,
            grid_points.lon,
            grid_points.geom,
            grid_points.geom
            <-> st_setsrid(st_makepoint(cities_in_area.lon, cities_in_area.lat), 4326) as dist
        from grid_points
        order by
            grid_points.geom
            <-> st_setsrid(st_makepoint(cities_in_area.lon, cities_in_area.lat), 4326)
        limit 4
    ) as nearest_four
    -- a place exactly on a border goes to the southern, then western, square
    order by nearest_four.dist, nearest_four.lat, nearest_four.lon
    limit 1
) as nearest
