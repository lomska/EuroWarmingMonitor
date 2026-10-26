-- Query plans and timings for the queries the app and the pipeline depend on.
-- Run from the project folder (Docker running), twice; use the second run
-- (the first warms the cache):
--   Get-Content perf\app_queries.sql | docker compose exec -T db psql -U postgres -d climate > perf\explain_<label>.txt

\pset pager off
-- 1-4 are the queries the app runs (app/data.py), for its default place, Paris;
-- 5-6 are the pipeline's. Numbers measured on the queries before these (the
-- rolling tables, read directly) are in explain_europe-before/after.txt.
\set place 'Paris'
set pg_trgm.word_similarity_threshold = 0.5;

\echo '==== 1. Place search with a typo ("Tbilsi"), as the app does it'
EXPLAIN (ANALYZE, BUFFERS)
select c.city_id, c.display_name, c.population,
       greatest(word_similarity('Tbilsi', c.city_name), coalesce(a.score, 0)) as score
from marts.dim_city as c
left join lateral (
    select alias, word_similarity('Tbilsi', alias) as score
    from unnest(string_to_array(c.alternate_names, ',')) as alias
    order by score desc
    limit 1
) as a on true
where 'Tbilsi' <% c.city_name or 'Tbilsi' <% c.alternate_names
order by score desc, c.population desc nulls last
limit 15;

\echo '==== 2. History of one grid cell: every year with its 10-year average (a view)'
EXPLAIN (ANALYZE, BUFFERS)
select month, year, temp_c, is_preliminary,
       rolling_start_year, rolling_avg_c, rolling_is_preliminary
from marts.mart_grid_history
where grid_point_id = (select grid_point_id from marts.dim_city
                       where city_name = :'place' order by population desc nulls last limit 1)
order by month, year;

\echo '==== 3. The three numbers of one grid cell: latest periods and trends'
EXPLAIN (ANALYZE, BUFFERS)
select l.month, l.year, l.temp_c, l.change_vs_normal_c, t.warming_c_per_decade
from marts.mart_grid_latest_period as l
left join marts.mart_grid_warming_trend as t
    on t.grid_point_id = l.grid_point_id and t.month = l.month
where l.grid_point_id = (select grid_point_id from marts.dim_city
                         where city_name = :'place' order by population desc nulls last limit 1);

\echo '==== 4. Map: the change of every cell in September against 1991-2020'
EXPLAIN (ANALYZE, BUFFERS)
select g.lat, g.lon, m.change_vs_normal_c as value, m.year
from marts.mart_grid_latest_period as m
inner join marts.dim_grid_point as g on m.grid_point_id = g.grid_point_id
where m.month = 9;

\echo '==== 5. Raw data for one month (partition pruning)'
EXPLAIN (ANALYZE, BUFFERS)
select avg(t2m_k) from raw.era5_t2m_monthly where valid_month = '1965-07-01';

\echo '==== 6. Rows an incremental dbt run must find (filter on loaded_at)'
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
