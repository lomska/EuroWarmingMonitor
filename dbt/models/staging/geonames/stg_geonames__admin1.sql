-- First-level regions (e.g. Imereti in Georgia), keyed like 'GE.66'.

with source as (

    select * from {{ source('geonames', 'geonames_admin1') }}

)

select
    code                           as admin1_key,
    split_part(code, '.', 1)       as country_code,
    split_part(code, '.', 2)       as admin1_code,
    name                           as admin1_name

from source
