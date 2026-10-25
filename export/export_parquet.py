"""Export the marts the app reads to Parquet files, so the app can run
without the database (for example as a public demo).

Each table is copied out of Postgres as CSV (fast, no Python objects per row),
then converted to Parquet with DuckDB: compressed, temperatures to the hundredth
of a degree, and sorted by grid square so the app reads only the part it needs.
The history table is split into one file per month (0 = the whole year), so no
file comes near GitHub's 100 MB limit.

Usage (from the project folder, with .venv active and the database running):
    python export/export_parquet.py              # writes data/app/
    python export/export_parquet.py --out other/folder
Then run the app on the files: set TEMPRADAR_SOURCE=parquet in .env.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import psycopg
import yaml
from dotenv import load_dotenv

log = logging.getLogger("export")

# Rows to leave out, per table (none at the moment): "table": "SQL condition"
FILTERS: dict[str, str] = {}

# Tables written as a folder of files, one per value of a column: <table>/<column>_NN.parquet
# (the app's data.py reads the same names)
SPLIT = {"mart_grid_history": "month"}

# Temperatures to the hundredth of a degree: stored as whole numbers, which compress
# far better than 4-byte floats (the history table: about half the size), and still
# ten times finer than the app shows. The app reads them back as ordinary numbers.
TEMP = "DECIMAL(5,2)"

# table -> columns and their Parquet (DuckDB) types, in order
EXPORTS = {
    "mart_grid_warming_trend": {
        "grid_point_id": "VARCHAR",
        "month": "TINYINT",
        "warming_c_per_decade": "FLOAT",
        "r_squared": "FLOAT",
        "first_year": "SMALLINT",
        "last_year": "SMALLINT",
    },
    "mart_grid_annual_warming_trend": {
        "grid_point_id": "VARCHAR",
        "warming_c_per_decade": "FLOAT",
        "r_squared": "FLOAT",
        "first_year": "SMALLINT",
        "last_year": "SMALLINT",
    },
    "dim_city": {
        "city_id": "BIGINT",
        "city_name": "VARCHAR",
        "ascii_name": "VARCHAR",
        "alternate_names": "VARCHAR",
        "display_name": "VARCHAR",
        "country_name": "VARCHAR",
        "admin1_name": "VARCHAR",
        "lat": "DOUBLE",
        "lon": "DOUBLE",
        "population": "BIGINT",
        "elevation_m": "INTEGER",
        "grid_point_id": "VARCHAR",
        "distance_to_grid_point_km": "FLOAT",
    },
    "dim_grid_point": {
        "grid_point_id": "VARCHAR",
        "lat": "DOUBLE",
        "lon": "DOUBLE",
        "land_fraction": "FLOAT",
        "area_km2": "FLOAT",
    },
    "mart_grid_latest_period": {
        "grid_point_id": "VARCHAR",
        "month": "TINYINT",
        "year": "SMALLINT",
        "temp_c": TEMP,
        "normal_c": TEMP,
        "early_normal_c": TEMP,
        "previous_year_temp_c": TEMP,
        "change_vs_normal_c": TEMP,
        "change_vs_early_normal_c": TEMP,
        "change_vs_previous_year_c": TEMP,
        "is_preliminary": "BOOLEAN",
    },
    # Every year with its 10-year average, for the history chart and its stripes
    "mart_grid_history": {
        "grid_point_id": "VARCHAR",
        "month": "TINYINT",
        "year": "SMALLINT",
        "temp_c": TEMP,
        "is_preliminary": "BOOLEAN",
        "rolling_start_year": "SMALLINT",
        "rolling_avg_c": TEMP,
        "rolling_is_preliminary": "BOOLEAN",
    },
}


def connect() -> psycopg.Connection:
    """Connect as the read-only reader role, the same access the app has."""
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user="reader",
        password=os.environ["READER_PASSWORD"],
    )


def export_table(pg, duck, table: str, columns: dict[str, str], out_dir: Path, tmp: Path) -> int:
    """Write one table (or its folder of files); returns its number of rows."""
    csv_path = tmp / f"{table}.csv"
    cols = ", ".join(columns)
    # Sorted by square, then month/year: the app reads one square at a time
    keys = ["grid_point_id"] + [c for c, kind in columns.items() if kind in ("TINYINT", "SMALLINT")]
    where = f"where {FILTERS[table]}" if table in FILTERS else ""
    query = f"select {cols} from marts.{table} {where} order by {', '.join(keys)}"
    copy_sql = f"COPY ({query}) TO STDOUT (FORMAT csv)"
    with csv_path.open("wb") as f, pg.cursor().copy(copy_sql) as copy:
        for block in copy:
            f.write(block)

    # Postgres's CSV dialect, stated rather than guessed: DuckDB's guess, made from a
    # sample of rows, can miss quotes written as "" inside a value (e.g. in place names)
    types = ", ".join(f"'{name}': '{kind}'" for name, kind in columns.items())
    rows_csv = f"""
        read_csv(
            '{csv_path.as_posix()}',
            header = false, delim = ',', quote = '"', escape = '"',
            auto_detect = false, columns = {{{types}}}
        )
    """
    options = "(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 100000)"

    if table not in SPLIT:
        target = out_dir / f"{table}.parquet"
        duck.execute(f"COPY (select * from {rows_csv}) TO '{target.as_posix()}' {options}")
        csv_path.unlink()
        return duck.execute(f"select count(*) from '{target.as_posix()}'").fetchone()[0]

    # One file per value: read the CSV once into DuckDB (on disk, in the temporary
    # folder), then write each part, keeping the rows' order
    column = SPLIT[table]
    folder = out_dir / table
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir()
    duck.execute(f"create or replace table split_rows as select * from {rows_csv}")
    csv_path.unlink()
    values = duck.execute(f"select distinct {column} from split_rows order by 1").fetchall()
    for (value,) in values:
        target = folder / f"{column}_{value:02d}.parquet"
        duck.execute(
            f"COPY (select * from split_rows where {column} = {value}) "
            f"TO '{target.as_posix()}' {options}"
        )
    rows = duck.execute("select count(*) from split_rows").fetchone()[0]
    duck.execute("drop table split_rows")
    return rows


def size_mb(out_dir: Path, table: str) -> float:
    """A table's file, or its folder of files, in MB."""
    files = list((out_dir / table).glob("*.parquet")) if table in SPLIT else []
    files = files or [out_dir / f"{table}.parquet"]
    return sum(f.stat().st_size for f in files) / 1e6


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/app"))
    parser.add_argument("--config", type=Path, default=Path("config/pipeline.yml"))
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    load_dotenv()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)

    # Remove files of tables the app no longer reads (or that are now split)
    for old in args.out.glob("*.parquet"):
        if old.stem not in EXPORTS or old.stem in SPLIT:
            old.unlink()
            log.info("removed %s (no longer exported)", old.name)

    with connect() as pg, tempfile.TemporaryDirectory() as tmp:
        # A database file in the temporary folder, so a split table needn't fit in memory
        duck = duckdb.connect(str(Path(tmp) / "export.duckdb"))
        for table, columns in EXPORTS.items():
            rows = export_table(pg, duck, table, columns, args.out, Path(tmp))
            log.info("%-32s %12s rows %8.1f MB", table, f"{rows:,}", size_mb(args.out, table))
        duck.close()

        last_year = pg.execute(
            "select max(year) from marts.mart_grid_history where month = 0"
        ).fetchone()[0]
        last_month = pg.execute(
            "select max(valid_month)::text from marts.fct_grid_monthly_temp"
            " where grid_point_id = (select min(grid_point_id) from marts.dim_grid_point)"
        ).fetchone()[0]

    metadata = {
        "study_area": cfg["study_area"]["name"],
        "data_until": last_month,
        "last_complete_year": last_year,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    total = sum(size_mb(args.out, table) for table in EXPORTS)
    largest = max(p.stat().st_size for p in args.out.rglob("*.parquet")) / 1e6
    log.info("wrote %s (%.0f MB in total, largest file %.0f MB)", args.out, total, largest)


if __name__ == "__main__":
    main()
