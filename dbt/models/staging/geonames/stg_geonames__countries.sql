-- Country codes and names.

with source as (

    select * from {{ source('geonames', 'geonames_countries') }}

)

select
    iso     as country_code,
    country as country_name

from source
