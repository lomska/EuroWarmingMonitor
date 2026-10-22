{#
    Use the schema names from dbt_project.yml exactly (staging, intermediate,
    marts) instead of dbt's default "<profile schema>_<custom schema>",
    which would give names like staging_marts.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
