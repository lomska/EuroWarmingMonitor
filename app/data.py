"""Where the app's data comes from: the marts in Postgres, or Parquet files.

Both sources answer the same questions with the same SQL (DuckDB reads the
Parquet files through views named like the marts); only the place search
differs, because Postgres uses pg_trgm and DuckDB its own similarity functions.

Chosen with TEMPRADAR_SOURCE in .env (or in Streamlit secrets):
    postgres  read the marts as the read-only reader role (default)
    parquet   read the files exported by: python pipeline.py export
              from TEMPRADAR_PARQUET: a folder, or an https:// address where the
              files are published (a GitHub release: export/publish_release.py).
              Files at an address are downloaded once, when the app starts, and
              then read from the local disk.
"""

from __future__ import annotations

import os
import re
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

import pandas as pd

# Tables the app reads, exported to Parquet under the same names
TABLES = [
    "dim_city",
    "dim_grid_point",
    "mart_grid_history",
    "mart_grid_latest_period",
    "mart_grid_warming_trend",
    "mart_grid_annual_warming_trend",
]

# Tables exported as one file per month (0 = the whole year), so no file comes near
# GitHub's 100 MB limit: <table>_month_00.parquet ... <table>_month_12.parquet, side by
# side with the others (a GitHub release has no folders). Written by
# export/export_parquet.py
SPLIT_BY_MONTH = ["mart_grid_history"]


def parquet_files(table: str) -> list[str]:
    """The file names a table is exported to."""
    if table in SPLIT_BY_MONTH:
        return [f"{table}_month_{m:02d}.parquet" for m in range(13)]
    return [f"{table}.parquet"]


def all_parquet_files() -> list[str]:
    """Every file of an export, as published: the tables and metadata.json."""
    return [name for table in TABLES for name in parquet_files(table)] + ["metadata.json"]


# The project folder (this file is in app/)
PROJECT = Path(__file__).resolve().parents[1]

# Base periods the map can compare with: label -> column of mart_grid_latest_period
BASES = {
    "1991–2020": "change_vs_normal_c",
    "1961–1990": "change_vs_early_normal_c",
}

SQL = {
    "place": """
        select city_id, city_name, display_name, country_name, admin1_name, lat, lon,
               population, elevation_m, grid_point_id, distance_to_grid_point_km
        from dim_city
        where city_id = :city_id
    """,
    "largest_place_in_square": """
        select city_id
        from dim_city
        where grid_point_id = :gp
        order by population desc nulls last
        limit 1
    """,
    "square": """
        select grid_point_id, lat, lon, land_fraction, area_km2
        from dim_grid_point
        where grid_point_id = :gp
    """,
    "latest": """
        select month, year, temp_c, normal_c, early_normal_c, previous_year_temp_c,
               change_vs_normal_c, change_vs_early_normal_c, change_vs_previous_year_c,
               is_preliminary
        from mart_grid_latest_period
        where grid_point_id = :gp
        order by month
    """,
    "trend": """
        select month, warming_c_per_decade, r_squared, first_year, last_year
        from mart_grid_warming_trend
        where grid_point_id = :gp
        order by month
    """,
    "annual_trend": """
        select warming_c_per_decade, r_squared, first_year, last_year
        from mart_grid_annual_warming_trend
        where grid_point_id = :gp
    """,
    # Every year of every month (1-12) and of the whole year (0): the single values
    # (the warming stripes) and the 10-year averages ending then (the line)
    "history": """
        select month, year, temp_c, is_preliminary,
               rolling_start_year, rolling_avg_c, rolling_is_preliminary
        from mart_grid_history
        where grid_point_id = :gp
        order by month, year
    """,
}

# Place search. Both return the best matches first, bigger places first among equals,
# and `alias`: the other name that matched, when it matched better than the place's own
# and is a different name, not a spelling of it (Mons for "Bergen", its Dutch name, but
# not "Tbilsi" for Tbilisi), so the list can say why the place is there.
# pg_trgm: word_similarity finds the typed text inside a name, with typos ("Tbilsi");
# the <% operator (word similarity >= 0.5, set below) uses the trigram indexes on dim_city.
SEARCH_POSTGRES = """
    select c.city_id, c.city_name, c.display_name, c.population,
           greatest(word_similarity(:q, c.city_name), coalesce(a.score, 0)) as score,
           case
               when a.score > word_similarity(:q, c.city_name)
                   and similarity(a.alias, c.city_name) < 0.4 then a.alias
           end as alias
    from dim_city as c
    left join lateral (
        select alias, word_similarity(:q, alias) as score
        from unnest(string_to_array(c.alternate_names, ',')) as alias
        order by score desc
        limit 1
    ) as a on true
    where :q <% c.city_name or :q <% c.alternate_names
    order by score desc, c.population desc nulls last
    limit :limit
"""

# DuckDB: Jaro-Winkler similarity rewards a matching start, so "Tbil" finds Tbilisi
SEARCH_DUCKDB = """
    with scored as (
        select city_id, city_name, display_name, population,
               greatest(
                   jaro_winkler_similarity(lower(city_name), lower(:q)),
                   jaro_winkler_similarity(lower(ascii_name), lower(:q))
               ) as name_score,
               -- the best other name, as {s: similarity, a: name}
               list_max(list_transform(
                   string_split(alternate_names, ','),
                   lambda x: {'s': jaro_winkler_similarity(lower(x), lower(:q)), 'a': x}
               )) as best
        from dim_city
    )
    select city_id, city_name, display_name, population,
           greatest(name_score, coalesce(best.s, 0)) as score,
           case
               when best.s > name_score
                   and jaro_winkler_similarity(lower(best.a), lower(city_name)) < 0.85
                   then best.a
           end as alias
    from scored
    where greatest(name_score, coalesce(best.s, 0)) >= 0.85
    order by round(score, 2) desc, population desc nulls last
    limit :limit
"""


class PostgresSource:
    """The marts in Postgres, read as the read-only reader role."""

    name = "postgres"

    def __init__(self) -> None:
        from sqlalchemy import URL, create_engine

        url = URL.create(
            "postgresql+psycopg",
            username="reader",
            password=os.environ["READER_PASSWORD"],
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.environ["POSTGRES_DB"],
        )
        # A few pooled connections, checked before use. Table names resolve to marts;
        # public holds the PostGIS and pg_trgm functions. A word similarity of 0.5
        # (default 0.6) still finds "Tbilsi" for Tbilisi
        self.engine = create_engine(
            url,
            pool_size=3,
            pool_pre_ping=True,
            connect_args={
                "options": (
                    "-c search_path=marts,public -c default_transaction_read_only=on"
                    " -c pg_trgm.word_similarity_threshold=0.5"
                )
            },
        )

    def query(self, sql: str, **params) -> pd.DataFrame:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            return pd.read_sql_query(text(sql), conn, params=params)

    def search(self, q: str, limit: int) -> pd.DataFrame:
        return self.query(SEARCH_POSTGRES, q=q, limit=limit)


class ParquetSource:
    """Parquet files exported from the marts, queried with DuckDB."""

    name = "parquet"

    def __init__(self, location: str) -> None:
        import duckdb

        self.location = Path(location)
        self.conn = duckdb.connect()
        for table in TABLES:
            files = ", ".join(f"'{(self.location / f).as_posix()}'" for f in parquet_files(table))
            self.conn.execute(f"create view {table} as select * from read_parquet([{files}])")

    def query(self, sql: str, **params) -> pd.DataFrame:
        # Same :name placeholders as SQLAlchemy; DuckDB writes them $name
        sql = re.sub(r"(?<!:):(\w+)", r"$\1", sql)
        # A cursor per query: DuckDB connections must not be shared between threads
        return self.conn.cursor().execute(sql, params).df()

    def search(self, q: str, limit: int) -> pd.DataFrame:
        return self.query(SEARCH_DUCKDB, q=q, limit=limit)


def open_source() -> PostgresSource | ParquetSource:
    kind = os.getenv("TEMPRADAR_SOURCE", "postgres")
    if kind == "postgres":
        return PostgresSource()
    if kind == "parquet":
        location = parquet_address()
        if location.startswith(("http://", "https://")):
            return ParquetSource(download(location))
        # A relative folder is the project's, also when the app runs from another folder
        if not Path(location).exists():
            location = str(PROJECT / location)
        return ParquetSource(location)
    raise ValueError(f"TEMPRADAR_SOURCE must be postgres or parquet, not {kind!r}")


def parquet_address() -> str:
    """Where the Parquet files are: a folder, or an https:// address."""
    return os.getenv("TEMPRADAR_PARQUET", "data/app")


def needs_download() -> bool:
    """Whether the app reads Parquet files from an address it hasn't downloaded yet."""
    address = parquet_address()
    return (
        os.getenv("TEMPRADAR_SOURCE") == "parquet"
        and address.startswith(("http://", "https://"))
        and address not in _DOWNLOADED
    )


# Address -> local folder: each address is downloaded once per app start
_DOWNLOADED: dict[str, str] = {}


def download(address: str, progress: Callable[[float, str], None] | None = None) -> str:
    """Download every file of an export from `address` (for example a GitHub release:
    https://github.com/<owner>/<repo>/releases/latest/download) into a new temporary
    folder, and return that folder. Reading the files there is as fast as on a laptop;
    reading them over the internet would make many small requests on every click.

    `progress(share, text)` is called as the files arrive (share from 0 to 1)."""
    if address in _DOWNLOADED:
        return _DOWNLOADED[address]
    folder = Path(tempfile.mkdtemp(prefix="tempradar-"))
    names = all_parquet_files()
    received = 0  # bytes
    for i, name in enumerate(names):
        part = folder / f"{name}.part"
        with urllib.request.urlopen(f"{address.rstrip('/')}/{name}", timeout=120) as response:
            with part.open("wb") as f:
                while block := response.read(1024 * 1024):
                    f.write(block)
                    received += len(block)
                    if progress:
                        # By file, plus the share of the current one
                        size = int(response.headers.get("Content-Length") or 0)
                        within = f.tell() / size if size else 0
                        progress(
                            (i + within) / len(names),
                            f"Downloading the data: {received / 1e6:.0f} MB, "
                            f"file {i + 1} of {len(names)}",
                        )
        part.rename(folder / name)  # only complete files get their real name
    _DOWNLOADED[address] = str(folder)
    return str(folder)


def map_sql(base: str) -> str:
    """Every square's change for one month (1-12) or the year (0), vs the base period."""
    return f"""
        select g.lat, g.lon, m.{BASES[base]} as value, m.year
        from mart_grid_latest_period as m
        inner join dim_grid_point as g on m.grid_point_id = g.grid_point_id
        where m.month = :month
    """
