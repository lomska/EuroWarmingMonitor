{#
    Convert a temperature in Kelvin to degrees Celsius.
    Usage: {{ kelvin_to_celsius('t2m_k') }}
#}
{% macro kelvin_to_celsius(column_name) -%}
    ({{ column_name }} - 273.15)
{%- endmacro %}
