{# Grid point id from coordinates in hundredths of a degree: 41.75, 44.5 -> '4175_4450'. #}
{% macro grid_point_id(lat_column, lon_column) -%}
    (round({{ lat_column }} * 100)::int || '_' || round({{ lon_column }} * 100)::int)
{%- endmacro %}
