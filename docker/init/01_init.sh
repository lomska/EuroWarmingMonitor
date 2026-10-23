#!/bin/bash
# Creates extensions, roles, schemas and permissions. Runs only when the
# database volume is empty; to run it again: docker compose down -v.
# Passwords come from .env. Keep LF line endings (CRLF breaks bash).

set -euo pipefail

# Stop with a clear message if a password is missing from .env
: "${LOADER_PASSWORD:?LOADER_PASSWORD is not set in .env}"
: "${TRANSFORMER_PASSWORD:?TRANSFORMER_PASSWORD is not set in .env}"
: "${READER_PASSWORD:?READER_PASSWORD is not set in .env}"

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -v db="$POSTGRES_DB" \
     -v loader_pw="$LOADER_PASSWORD" \
     -v transformer_pw="$TRANSFORMER_PASSWORD" \
     -v reader_pw="$READER_PASSWORD" \
     <<'EOSQL'

-- 1. Extensions ---------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;   -- points, squares, distances
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fuzzy text matching for the city search


-- 2. Roles --------------------------------------------------------------
CREATE ROLE loader      LOGIN PASSWORD :'loader_pw';       -- Python load step
CREATE ROLE transformer LOGIN PASSWORD :'transformer_pw';  -- dbt
CREATE ROLE reader      LOGIN PASSWORD :'reader_pw';       -- Streamlit app


-- 3. Database-level access ----------------------------------------------
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO loader, transformer, reader;

-- dbt creates schemas (stored test failures) and temp tables (incremental models)
GRANT CREATE, TEMPORARY ON DATABASE :"db" TO transformer;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;


-- 4. Schemas, each owned by the role that writes to it ------------------
CREATE SCHEMA raw          AUTHORIZATION loader;
CREATE SCHEMA staging      AUTHORIZATION transformer;
CREATE SCHEMA intermediate AUTHORIZATION transformer;
CREATE SCHEMA marts        AUTHORIZATION transformer;


-- 5. transformer reads raw -----------------------------------------------
GRANT USAGE ON SCHEMA raw TO transformer;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO transformer;

-- Tables created later must be created by loader for this to apply
ALTER DEFAULT PRIVILEGES FOR ROLE loader IN SCHEMA raw
    GRANT SELECT ON TABLES TO transformer;


-- 6. reader reads marts ---------------------------------------------------
GRANT USAGE ON SCHEMA marts TO reader;
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO reader;

ALTER DEFAULT PRIVILEGES FOR ROLE transformer IN SCHEMA marts
    GRANT SELECT ON TABLES TO reader;

EOSQL

echo "01_init.sh: extensions, roles and schemas created"
