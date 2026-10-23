"""Load the GeoNames place lists into Postgres (schema raw), unchanged.

Every value is loaded as text, exactly as in the file; dbt casts the types.
Safe to re-run: an unchanged file is skipped, a changed one replaces its
table's contents in one transaction.

Usage (from the project folder, with .venv active and the database running):
    python load/load_geonames.py
    python load/load_geonames.py --force   # reload even if unchanged
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

import pandas as pd
import yaml

from common import connect, logged_checksums, record_load, setup_logging, sha256, to_csv

log = logging.getLogger("load")

DEFAULT_CONFIG = Path("config/pipeline.yml")

# file name -> (raw table, column names in file order, as in the GeoNames readme)
FILES = {
    "cities1000.txt": ("raw.geonames_cities", [
        "geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude",
        "feature_class", "feature_code", "country_code", "cc2", "admin1_code",
        "admin2_code", "admin3_code", "admin4_code", "population", "elevation",
        "dem", "timezone", "modification_date",
    ]),
    "admin1CodesASCII.txt": ("raw.geonames_admin1", [
        "code", "name", "asciiname", "geonameid",
    ]),
    "countryInfo.txt": ("raw.geonames_countries", [
        "iso", "iso3", "iso_numeric", "fips", "country", "capital", "area_sq_km",
        "population", "continent", "tld", "currency_code", "currency_name", "phone",
        "postal_code_format", "postal_code_regex", "languages", "geonameid",
        "neighbours", "equivalent_fips_code",
    ]),
}


def read_geonames(path: Path, columns: list[str]) -> pd.DataFrame:
    """Read a GeoNames tab-separated file with every value as text.

    keep_default_na=False matters: otherwise pandas would turn Namibia's
    country code "NA" (and empty fields) into missing values.
    Lines starting with '#' are comments (countryInfo.txt has a long header).
    """
    df = pd.read_csv(
        path,
        sep="\t",
        header=None,
        names=columns,
        dtype=str,
        keep_default_na=False,
        quoting=csv.QUOTE_NONE,
        comment=None,
        encoding="utf-8",
    )
    first = columns[0]
    return df[~df[first].str.startswith("#")]


def load_file(conn, path: Path, table: str, columns: list[str], checksum: str) -> int:
    df = read_geonames(path, columns)
    df["source_file"] = path.name
    with conn.transaction():
        conn.execute(f"DELETE FROM {table}")
        cols = ", ".join(df.columns)
        with conn.cursor().copy(f"COPY {table} ({cols}) FROM STDIN (FORMAT csv)") as copy:
            copy.write(to_csv(df))
        record_load(conn, path.name, table, len(df), checksum)
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--force", action="store_true", help="reload files even if unchanged")
    args = parser.parse_args()
    setup_logging()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    geo_dir = Path(cfg["geonames"]["dir"])

    missing = [name for name in FILES if not (geo_dir / name).exists()]
    if missing:
        raise SystemExit(
            f"Missing in {geo_dir}: {', '.join(missing)}. "
            "Run extract/download_geonames.py first."
        )

    with connect() as conn:
        logged = logged_checksums(conn)
        for name, (table, columns) in FILES.items():
            path = geo_dir / name
            checksum = sha256(path)
            if not args.force and logged.get(name) == checksum:
                log.info("skip %s (already loaded, unchanged)", name)
                continue
            rows = load_file(conn, path, table, columns, checksum)
            log.info("loaded %s: %s rows into %s", name, f"{rows:,}", table)
            conn.execute(f"ANALYZE {table}")


if __name__ == "__main__":
    main()
