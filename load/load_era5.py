"""Load the downloaded ERA5 NetCDF files into Postgres (schema raw).

The data goes in exactly as it came, only reshaped from grids into rows
(one row per grid point and month).

Safe to re-run:
  * a file already loaded and unchanged on disk is skipped;
  * a changed file replaces its own earlier rows in one transaction;
  * rows from files no longer on disk (outdated downloads) are removed.

Usage (from the project folder, with .venv active and the database running):
    python load/load_era5.py           # load new or changed files
    python load/load_era5.py --force   # reload every file
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import xarray as xr
import yaml

from common import connect, logged_checksums, record_load, setup_logging, sha256, to_csv

log = logging.getLogger("load")

DEFAULT_CONFIG = Path("config/pipeline.yml")
T2M_TABLE = "raw.era5_t2m_monthly"
LSM_TABLE = "raw.era5_land_sea_mask"
LSM_FILE = "era5_land_sea_mask.nc"


def month_range(ds: xr.Dataset) -> tuple[date, date]:
    times = pd.to_datetime(ds["valid_time"].values)
    return times.min().date(), times.max().date()


# --- loading one file ----------------------------------------------------------

def t2m_rows(ds: xr.Dataset, months: slice, source_file: str) -> pd.DataFrame:
    """Reshape a block of months from grid (time x lat x lon) to long rows."""
    block = ds.isel(valid_time=months)
    df = block["t2m"].to_dataframe().reset_index()
    expver = block["expver"].to_series() if "expver" in block.coords else None
    return pd.DataFrame({
        "lat": df["latitude"],
        "lon": df["longitude"],
        "valid_month": df["valid_time"].dt.date,
        "t2m_k": df["t2m"],
        "expver": df["valid_time"].map(expver) if expver is not None else None,
        "source_file": source_file,
    })


def load_t2m_file(conn, path: Path, checksum: str, months_per_batch: int) -> int:
    """Replace this file's rows in raw.era5_t2m_monthly, in one transaction."""
    with xr.open_dataset(path) as ds, conn.transaction():
        first, last = month_range(ds)
        expected = ds.sizes["valid_time"] * ds.sizes["latitude"] * ds.sizes["longitude"]

        # Remove this file's earlier rows; the date range limits it to its partitions
        conn.execute(
            f"DELETE FROM {T2M_TABLE} WHERE source_file = %s "
            "AND valid_month BETWEEN %s AND %s",
            (path.name, first, last),
        )

        copied = 0
        cols = "lat, lon, valid_month, t2m_k, expver, source_file"
        with conn.cursor().copy(f"COPY {T2M_TABLE} ({cols}) FROM STDIN (FORMAT csv)") as copy:
            # A few months at a time keeps memory small even for global files
            for start in range(0, ds.sizes["valid_time"], months_per_batch):
                df = t2m_rows(ds, slice(start, start + months_per_batch), path.name)
                copy.write(to_csv(df))
                copied += len(df)

        if copied != expected:
            raise RuntimeError(f"{path.name}: copied {copied} rows, expected {expected}")
        record_load(conn, path.name, T2M_TABLE, copied, checksum, first, last)
    return copied


def load_lsm_file(conn, path: Path, checksum: str) -> int:
    """Replace the whole land-sea mask table, in one transaction."""
    with xr.open_dataset(path) as ds, conn.transaction():
        lsm = ds["lsm"]
        if "valid_time" in lsm.dims:  # the mask comes as a single month
            lsm = lsm.isel(valid_time=0)
        df = lsm.to_dataframe().reset_index()
        rows = pd.DataFrame({
            "lat": df["latitude"],
            "lon": df["longitude"],
            "lsm": df["lsm"],
            "source_file": path.name,
        })
        conn.execute(f"DELETE FROM {LSM_TABLE}")
        with conn.cursor().copy(
            f"COPY {LSM_TABLE} (lat, lon, lsm, source_file) FROM STDIN (FORMAT csv)"
        ) as copy:
            copy.write(to_csv(rows))
        record_load(conn, path.name, LSM_TABLE, len(rows), checksum, None, None)
    return len(rows)


def remove_outdated(conn, files_on_disk: set[str]) -> None:
    """Delete rows of temperature files that are logged but no longer on disk.

    download_era5.py removes outdated files (e.g. ..._202601_202609.nc once
    ..._202601_202610.nc exists); this keeps the database in step with that.
    """
    logged = conn.execute(
        "SELECT source_file, first_month, last_month FROM raw._load_log "
        "WHERE target_table = %s",
        (T2M_TABLE,),
    ).fetchall()
    for source_file, first, last in logged:
        if source_file in files_on_disk:
            continue
        with conn.transaction():
            cur = conn.execute(
                f"DELETE FROM {T2M_TABLE} WHERE source_file = %s "
                "AND valid_month BETWEEN %s AND %s",
                (source_file, first, last),
            )
            conn.execute("DELETE FROM raw._load_log WHERE source_file = %s", (source_file,))
        log.info("removed %s rows of outdated %s", f"{cur.rowcount:,}", source_file)


def check_totals(conn, cfg: dict) -> None:
    """Row count should equal grid points x months in the configured period."""
    end_year, end_month = (int(p) for p in cfg["period"]["end_month"].split("-"))
    months = (end_year - cfg["period"]["start_year"]) * 12 + end_month
    points = conn.execute(f"SELECT count(*) FROM {LSM_TABLE}").fetchone()[0]
    rows = conn.execute(f"SELECT count(*) FROM {T2M_TABLE}").fetchone()[0]
    expected = points * months
    status = "OK" if rows == expected else "MISMATCH"
    log.info(
        "%s: %s rows in %s, expected %s (%s grid points x %s months)",
        status, f"{rows:,}", T2M_TABLE, f"{expected:,}", f"{points:,}", months,
    )


# --- main ----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--force", action="store_true", help="reload files even if unchanged")
    args = parser.parse_args()

    setup_logging()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    raw_dir = Path(cfg["paths"]["raw_dir"])
    months_per_batch = cfg.get("load", {}).get("months_per_batch", 12)

    t2m_files = sorted(raw_dir.glob("era5_t2m_*.nc"))
    lsm_path = raw_dir / LSM_FILE
    if not t2m_files or not lsm_path.exists():
        raise SystemExit(f"No ERA5 files in {raw_dir}. Run extract/download_era5.py first.")

    with connect() as conn:
        logged = logged_checksums(conn)

        remove_outdated(conn, {p.name for p in t2m_files})

        for path in [lsm_path, *t2m_files]:
            checksum = sha256(path)
            if not args.force and logged.get(path.name) == checksum:
                log.info("skip %s (already loaded, unchanged)", path.name)
                continue
            if path == lsm_path:
                rows = load_lsm_file(conn, path, checksum)
            else:
                rows = load_t2m_file(conn, path, checksum, months_per_batch)
            log.info("loaded %s: %s rows", path.name, f"{rows:,}")

        # Update planner statistics after the load
        conn.execute(f"ANALYZE {T2M_TABLE}")
        conn.execute(f"ANALYZE {LSM_TABLE}")

        check_totals(conn, cfg)


if __name__ == "__main__":
    main()
