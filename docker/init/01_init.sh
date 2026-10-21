#!/bin/bash
# Runs once, when the database volume is empty (Postgres's docker-entrypoint).
# Creates the extensions, the three project roles and the four schemas,
# and sets who may read or write where.
#
# Bash rather than plain .sql so the role passwords can come from .env
# (passed in by docker-compose.yml) instead of being written in the repo.
#
# IMPORTANT: this file must use LF line endings, not Windows CRLF.

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
-- Installed in the public schema, which every role can use.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_raster;  -- required by h3_postgis
CREATE EXTENSION IF NOT EXISTS h3;
CREATE EXTENSION IF NOT EXISTS h3_postgis;


-- 2. Roles --------------------------------------------------------------
-- LOGIN lets them connect; they get no other powers by default.
CREATE ROLE loader      LOGIN PASSWORD :'loader_pw';       -- Python load step
CREATE ROLE transformer LOGIN PASSWORD :'transformer_pw';  -- dbt
CREATE ROLE reader      LOGIN PASSWORD :'reader_pw';       -- Streamlit app


-- 3. Database-level access ----------------------------------------------
-- Only our roles (and the superuser) may connect.
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO loader, transformer, reader;

-- dbt may create extra schemas of its own (e.g. for stored test failures).
GRANT CREATE ON DATABASE :"db" TO transformer;

-- Nobody creates objects in public; extension functions there stay usable.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;


-- 4. Schemas, each owned by the role that writes to it ------------------
-- The owner can create, replace and drop anything inside its schema.
CREATE SCHEMA raw          AUTHORIZATION loader;
CREATE SCHEMA staging      AUTHORIZATION transformer;
CREATE SCHEMA intermediate AUTHORIZATION transformer;
CREATE SCHEMA marts        AUTHORIZATION transformer;


-- 5. transformer reads raw -----------------------------------------------
GRANT USAGE ON SCHEMA raw TO transformer;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO transformer;   -- tables that exist now (none yet)

-- ...and every table loader creates in raw from now on
ALTER DEFAULT PRIVILEGES FOR ROLE loader IN SCHEMA raw
    GRANT SELECT ON TABLES TO transformer;


-- 6. reader reads marts ---------------------------------------------------
GRANT USAGE ON SCHEMA marts TO reader;
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO reader;

-- ...and every table or view dbt (transformer) builds in marts from now on
ALTER DEFAULT PRIVILEGES FOR ROLE transformer IN SCHEMA marts
    GRANT SELECT ON TABLES TO reader;

EOSQL

echo "01_init.sh: extensions, roles and schemas created"
