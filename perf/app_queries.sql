-- Query plans and timings for the queries the app and the pipeline depend on.
-- Run from the project folder (Docker running), twice; use the second run
-- (the first warms the cache):
--   Get-Content perf\app_queries.sql | docker compose exec -T db psql -U postgres -d climate > perf\explain_<label>.txt

\pset pager off
\set place 'Tbilisi'

\echo '==== 1. City search with a typo ("Tbilsi")'
EXPLAIN (ANALYZE, BUFFERS)
select city_id, display_name, population
from marts.dim_city
where city_name % 'Tbilsi' or alternate_names ilike '%Tbilsi%'
order by similarity(city_name, 'Tbilsi') desc, population desc nulls last
limit 10;

\echo '==== 2. Monthly temperatures of one square (largest mart)'
EXPLAIN (ANALYZE, BUFFERS)
select valid_month, temp_c
from marts.fct_grid_monthly_temp
where grid_point_id = (select grid_point_id from marts.dim_city
                       where city_name = :'place' order by population desc nulls last limit 1)
order by valid_month;

\echo '==== 3. Monthly 10-year means of one square'
EXPLAIN (ANALYZE, BUFFERS)
select month, window_end_year, avg_temp_c
from marts.fct_grid_rolling_10y
where grid_point_id = (select grid_point_id from marts.dim_city
                       where city_name = :'place' order by population desc nulls last limit 1);

\echo '==== 4. Annual 10-year means of one square'
EXPLAIN (ANALYZE, BUFFERS)
select window_end_year, avg_temp_c
from marts.fct_grid_rolling_10y_annual
where grid_point_id = (select grid_point_id from marts.dim_city
                       where city_name = :'place' order by population desc nulls last limit 1);

\echo '==== 5. Map: July warming per square, with the square polygons'
EXPLAIN (ANALYZE, BUFFERS)
select g.grid_point_id, g.square, t.warming_c_per_decade
from marts.mart_grid_warming_trend t
join marts.dim_grid_point g using (grid_point_id)
where t.month = 7;

\echo '==== 6. Raw data for one month (partition pruning)'
EXPLAIN (ANALYZE, BUFFERS)
select avg(t2m_k) from raw.era5_t2m_monthly where valid_month = '1965-07-01';

\echo '==== 7. Rows an incremental dbt run must find (filter on loaded_at)'
EXPLAIN (ANALYZE, BUFFERS)
select count(*) from raw.era5_t2m_monthly
where loaded_at > (select max(source_loaded_at) from marts.fct_grid_monthly_temp);

\echo '==== Table sizes'
select schemaname || '.' || relname as table_name,
       pg_size_pretty(pg_total_relation_size(relid)) as total_size,
       n_live_tup as approx_rows
from pg_stat_user_tables
where schemaname in ('raw', 'marts', 'intermediate')
order by pg_total_relation_size(relid) desc
limit 15;
