-- Raw tables for ERA5 data, exactly as downloaded (only reshaped into rows).
--
-- Run as the LOADER role (load_era5.py does this on every run), so the
-- default privileges from docker/init give dbt's transformer role read access.
-- Every statement is safe to run again.


-- Monthly 2 m temperature, one row per grid point and month ------------
CREATE TABLE IF NOT EXISTS raw.era5_t2m_monthly (
    lat          real        NOT NULL,  -- degrees north (0.25° steps are exact in real)
    lon          real        NOT NULL,  -- degrees east
    valid_month  date        NOT NULL,  -- first day of the month
    t2m_k        real,                  -- 2 m temperature in Kelvin, as delivered
    expver       text,                  -- ERA5 version label: final or preliminary (ERA5T)
    source_file  text        NOT NULL,  -- NetCDF file the row came from
    loaded_at    timestamptz NOT NULL DEFAULT now()
) PARTITION BY RANGE (valid_month);

-- One partition per decade. A query for one period reads only its partitions.
CREATE TABLE IF NOT EXISTS raw.era5_t2m_monthly_1940s PARTITION OF raw.era5_t2m_monthly
    FOR VALUES FROM ('1940-01-01') TO ('1950-01-01');
CREATE TABLE IF NOT EXISTS raw.era5_t2m_monthly_1950s PARTITION OF raw.era5_t2m_monthly
    FOR VALUES FROM ('1950-01-01') TO ('1960-01-01');
CREATE TABLE IF NOT EXISTS raw.era5_t2m_monthly_1960s PARTITION OF raw.era5_t2m_monthly
    FOR VALUES FROM ('1960-01-01') TO ('1970-01-01');
CREATE TABLE IF NOT EXISTS raw.era5_t2m_monthly_1970s PARTITION OF raw.era5_t2m_monthly
    FOR VALUES FROM ('1970-01-01') TO ('1980-01-01');
CREATE TABLE IF NOT EXISTS raw.era5_t2m_monthly_1980s PARTITION OF raw.era5_t2m_monthly
    FOR VALUES FROM ('1980-01-01') TO ('1990-01-01');
CREATE TABLE IF NOT EXISTS raw.era5_t2m_monthly_1990s PARTITION OF raw.era5_t2m_monthly
    FOR VALUES FROM ('1990-01-01') TO ('2000-01-01');
CREATE TABLE IF NOT EXISTS raw.era5_t2m_monthly_2000s PARTITION OF raw.era5_t2m_monthly
    FOR VALUES FROM ('2000-01-01') TO ('2010-01-01');
CREATE TABLE IF NOT EXISTS raw.era5_t2m_monthly_2010s PARTITION OF raw.era5_t2m_monthly
    FOR VALUES FROM ('2010-01-01') TO ('2020-01-01');
CREATE TABLE IF NOT EXISTS raw.era5_t2m_monthly_2020s PARTITION OF raw.era5_t2m_monthly
    FOR VALUES FROM ('2020-01-01') TO ('2030-01-01');

-- Catches any date outside the decades above instead of failing the load.
CREATE TABLE IF NOT EXISTS raw.era5_t2m_monthly_default PARTITION OF raw.era5_t2m_monthly
    DEFAULT;


-- Land-sea mask, one row per grid point -----------------------------------
CREATE TABLE IF NOT EXISTS raw.era5_land_sea_mask (
    lat          real        NOT NULL,
    lon          real        NOT NULL,
    lsm          real,                  -- land fraction: 0 = sea, 1 = land
    source_file  text        NOT NULL,
    loaded_at    timestamptz NOT NULL DEFAULT now()
);


-- One row per loaded file: what was loaded, when, and from which version ---
CREATE TABLE IF NOT EXISTS raw._load_log (
    source_file  text        PRIMARY KEY,
    target_table text        NOT NULL,
    row_count    bigint      NOT NULL,
    checksum     text        NOT NULL,  -- SHA-256 of the file: unchanged file = skip
    first_month  date,                  -- time range in the file (NULL for the mask)
    last_month   date,
    loaded_at    timestamptz NOT NULL DEFAULT now()
);
