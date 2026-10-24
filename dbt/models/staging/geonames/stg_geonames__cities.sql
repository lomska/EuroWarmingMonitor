-- Places from GeoNames with proper types. One row per place.

with source as (

    select * from {{ source('geonames', 'geonames_cities') }}

),

renamed as (

    select
        geonameid::bigint                     as city_id,
        name                                  as city_name,
        asciiname                             as ascii_name,
        nullif(alternatenames, '')            as alternate_names,
        latitude::double precision            as lat,
        longitude::double precision           as lon,
        feature_code,
        country_code,
        nullif(admin1_code, '')               as admin1_code,
        nullif(population, '')::bigint        as population,
        nullif(elevation, '')::int            as elevation_m,
        -- -9999 means "no data" in the elevation model
        nullif(nullif(dem, ''), '-9999')::int as dem_elevation_m,
        timezone

    from source

)

select * from renamed
