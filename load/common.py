"""Helpers shared by the load scripts (load_era5.py, load_geonames.py)."""

from __future__ import annotations

import hashlib
import io
import logging
import os
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

DDL_FILE = Path(__file__).parent / "ddl" / "raw_tables.sql"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def connect() -> psycopg.Connection:
    """Connect as the loader role, with settings from .env, and create raw tables if missing."""
    load_dotenv()
    conn = psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user="loader",
        password=os.environ["LOADER_PASSWORD"],
    )
    conn.autocommit = True  # each file gets its own explicit transaction
    # Tables must be created by the loader role, so dbt's role can read them
    conn.execute(DDL_FILE.read_text(encoding="utf-8"))
    return conn


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def to_csv(df: pd.DataFrame) -> str:
    """CSV text for COPY. Missing values become empty fields, which COPY reads as NULL."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    return buf.getvalue()


def logged_checksums(conn) -> dict[str, str]:
    return dict(conn.execute("SELECT source_file, checksum FROM raw._load_log").fetchall())


def record_load(conn, source_file, table, rows, checksum, first=None, last=None) -> None:
    conn.execute(
        """
        INSERT INTO raw._load_log
            (source_file, target_table, row_count, checksum, first_month, last_month)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_file) DO UPDATE SET
            target_table = EXCLUDED.target_table,
            row_count    = EXCLUDED.row_count,
            checksum     = EXCLUDED.checksum,
            first_month  = EXCLUDED.first_month,
            last_month   = EXCLUDED.last_month,
            loaded_at    = now()
        """,
        (source_file, table, rows, checksum, first, last),
    )
