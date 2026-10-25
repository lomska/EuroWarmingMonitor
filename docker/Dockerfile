# Postgres 17 + PostGIS 3.6, with the project's setup script built in.
# Published to GitHub Container Registry by .github/workflows/image.yml.
FROM postgis/postgis:17-3.6

LABEL org.opencontainers.image.source=https://github.com/lomska/EuroWarmingMonitor
LABEL org.opencontainers.image.description="Euro Warming Monitor database: Postgres 17, PostGIS, pg_trgm, project roles and schemas"

# Runs once, when the database is first created (on an empty volume)
COPY --chmod=755 init/ /docker-entrypoint-initdb.d/
