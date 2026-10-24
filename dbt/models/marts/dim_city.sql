-- Places in the study area that can be searched, with their grid square.

-- Trigram indexes for fast, typo-tolerant name search in the app
-- (here rather than in YAML so that {{ this }} is filled in at run time).
{{
    config(
        post_hook=[
            "create index if not exists dim_city_name_trgm on {{ this }} using gin (city_name gin_trgm_ops)",
            "create index if not exists dim_city_alt_names_trgm on {{ this }} using gin (alternate_names gin_trgm_ops)"
        ]
    )
}}

with cities as (

    select * from {{ ref('stg_geonames__cities') }}

),

city_grid as (

    select * from {{ ref('int_city_grid_point') }}

),

admin1 as (

    select * from {{ ref('stg_geonames__admin1') }}

),

countries as (

    select * from {{ ref('stg_geonames__countries') }}

)

select
    cities.city_id,
    cities.city_name,
    cities.ascii_name,
    cities.alternate_names,
    -- What the search results show, e.g. "Kutaisi, Imereti, Georgia"
    concat_ws(', ', cities.city_name, admin1.admin1_name, countries.country_name)
                                                          as display_name,
    cities.country_code,
    countries.country_name,
    admin1.admin1_name,
    cities.lat,
    cities.lon,
    cities.population,
    coalesce(cities.elevation_m, cities.dem_elevation_m)  as elevation_m,
    city_grid.grid_point_id,
    city_grid.distance_km                                 as distance_to_grid_point_km

from city_grid
inner join cities
    on cities.city_id = city_grid.city_id
left join admin1
    on  admin1.country_code = cities.country_code
    and admin1.admin1_code = cities.admin1_code
left join countries
    on countries.country_code = cities.country_code
