-- Raw tables for ERA5 data, exactly as downloaded (only reshaped into rows).
--
-- Run as the LOADER role (load_era5.py does this on every run), so the
-- default privileges from docker/init give dbt's transformer role read access.
-- Every statement is safe to run again.


-- Monthly 2 m temperature, one row per grid point and month ------------
CREATE TABLE IF NOT EXISTS raw.era5_t2m_monthly (
    lat          real        NOT NULL,  -- degrees north
    lon          real        NOT NULL,  -- degrees east
    valid_month  date        NOT NULL,  -- first day of the month
    t2m_k        real,                  -- 2 m temperature in Kelvin, as delivered
    expver       text,                  -- ERA5 version label: final or preliminary (ERA5T)
    source_file  text        NOT NULL,  -- NetCDF file the row came from
    loaded_at    timestamptz NOT NULL DEFAULT now()
) PARTITION BY RANGE (valid_month);

-- One partition per decade.
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


-- BRIN indexes: tiny, and suited to columns that grow with insertion order.
-- loaded_at lets incremental dbt runs skip old rows; valid_month narrows
-- month queries inside a decade partition.
CREATE INDEX IF NOT EXISTS era5_t2m_monthly_loaded_at_brin
    ON raw.era5_t2m_monthly USING brin (loaded_at);
CREATE INDEX IF NOT EXISTS era5_t2m_monthly_valid_month_brin
    ON raw.era5_t2m_monthly USING brin (valid_month);

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


-- GeoNames place lists, loaded as text exactly as in the files ------------
-- (types are cast in dbt staging). Column names follow the GeoNames readme.
CREATE TABLE IF NOT EXISTS raw.geonames_cities (
    geonameid          text,
    name               text,
    asciiname          text,
    alternatenames     text,
    latitude           text,
    longitude          text,
    feature_class      text,
    feature_code       text,
    country_code       text,
    cc2                text,
    admin1_code        text,
    admin2_code        text,
    admin3_code        text,
    admin4_code        text,
    population         text,
    elevation          text,
    dem                text,   -- digital elevation model height (-9999 = none)
    timezone           text,
    modification_date  text,
    source_file        text        NOT NULL,
    loaded_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.geonames_admin1 (
    code               text,   -- country.admin1, e.g. GE.66
    name               text,
    asciiname          text,
    geonameid          text,
    source_file        text        NOT NULL,
    loaded_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.geonames_countries (
    iso                text,
    iso3               text,
    iso_numeric        text,
    fips               text,
    country            text,
    capital            text,
    area_sq_km         text,
    population         text,
    continent          text,
    tld                text,
    currency_code      text,
    currency_name      text,
    phone              text,
    postal_code_format text,
    postal_code_regex  text,
    languages          text,
    geonameid          text,
    neighbours         text,
    equivalent_fips_code text,
    source_file        text        NOT NULL,
    loaded_at          timestamptz NOT NULL DEFAULT now()
);
