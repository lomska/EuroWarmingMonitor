{#
    A readable, stable id for an ERA5 grid point, from its coordinates in
    hundredths of a degree: lat 41.75, lon 44.5 -> '4175_4450'.
    Integers avoid floating-point surprises when the id is compared or joined.
#}
{% macro grid_point_id(lat_column, lon_column) -%}
    (round({{ lat_column }} * 100)::int || '_' || round({{ lon_column }} * 100)::int)
{%- endmacro %}
