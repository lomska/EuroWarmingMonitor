"""Run the TempRadar pipeline, or any of its steps, with one command.

Steps, in order:
    extract    download ERA5 and GeoNames files            (extract/*.py)
    load       copy new or changed files into schema raw    (load/*.py)
    transform  dbt build: build every model and run its tests
    test       dbt source freshness + dbt test, without rebuilding
    docs       dbt docs as one static page: docs/index.html
    all        extract, load, then transform and docs only if something new was loaded

Usage (from the project folder, with .venv active and the database running):
    python pipeline.py                     # same as: python pipeline.py all
    python pipeline.py load transform      # several steps, run in the order given
    python pipeline.py all --force         # rebuild even if nothing new was loaded
    python pipeline.py transform --full-refresh   # after changing grid, area or columns

Settings come from .env (passwords, port) and config/pipeline.yml (area, period).
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DBT_DIR = ROOT / "dbt"
DEFAULT_CONFIG = Path("config/pipeline.yml")
# When the last successful build started from; compared with the load log
LAST_BUILD_FILE = ROOT / "data" / "last_build.txt"

STEPS = ["extract", "load", "transform", "test", "docs", "all"]

log = logging.getLogger("pipeline")


class StepFailed(Exception):
    pass


def run(cmd: list[str], cwd: Path = ROOT, shown: str | None = None) -> None:
    """Run a command, streaming its output; stop the pipeline if it fails."""
    shown = shown or " ".join(cmd)
    log.info("$ %s", shown)
    if subprocess.run(cmd, cwd=cwd).returncode != 0:
        raise StepFailed(shown)


def dbt(*args: str, target: str) -> None:
    """Run dbt from this Python environment, so a global dbt is never picked up."""
    if importlib.util.find_spec("dbt") is None:
        raise SystemExit("dbt is not installed in this environment. Activate .venv first.")
    args = (*args, "--target", target)
    # Same as typing "dbt ...", but with this Python's dbt
    cmd = [sys.executable, "-c", "import sys; from dbt.cli.main import cli; sys.exit(cli())"]
    run([*cmd, *args], cwd=DBT_DIR, shown="dbt " + " ".join(args))


def python(script: str, config: Path) -> None:
    run([sys.executable, script, "--config", str(config)])


# --- new data? -------------------------------------------------------------------


def latest_load() -> str | None:
    """When the most recent file was loaded into raw (None if nothing is loaded)."""
    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user="loader",
        password=os.environ["LOADER_PASSWORD"],
    ) as conn:
        try:
            row = conn.execute("SELECT max(loaded_at)::text FROM raw._load_log").fetchone()
        except psycopg.errors.UndefinedTable:  # the loaders haven't run yet
            return None
    return row[0]


def last_build() -> str | None:
    return LAST_BUILD_FILE.read_text().strip() if LAST_BUILD_FILE.exists() else None


# --- steps -----------------------------------------------------------------------


def extract(args) -> None:
    python("extract/download_geonames.py", args.config)
    python("extract/download_era5.py", args.config)


def load(args) -> None:
    python("load/load_geonames.py", args.config)
    python("load/load_era5.py", args.config)


def transform(args) -> None:
    loaded = latest_load()
    if not (DBT_DIR / "dbt_packages").exists():
        dbt("deps", target=args.target)
    build = ["build"] + (["--full-refresh"] if args.full_refresh else [])
    dbt(*build, target=args.target)
    # Only written after a successful build, so a failed one is retried next time
    if loaded:
        LAST_BUILD_FILE.parent.mkdir(exist_ok=True)
        LAST_BUILD_FILE.write_text(loaded)


def test(args) -> None:
    dbt("source", "freshness", target=args.target)
    dbt("test", target=args.target)


def docs(args) -> None:
    dbt("docs", "generate", "--static", target=args.target)
    target = ROOT / "docs" / "index.html"
    target.parent.mkdir(exist_ok=True)
    shutil.copyfile(DBT_DIR / "target" / "static_index.html", target)
    log.info("docs written to %s", target.relative_to(ROOT))


def run_all(args) -> None:
    extract(args)
    load(args)
    loaded, built = latest_load(), last_build()
    if not args.force and loaded is not None and loaded == built:
        log.info("nothing new loaded since the last build (%s): skipping dbt", built)
        return
    transform(args)
    docs(args)


RUNNERS = {
    "extract": extract,
    "load": load,
    "transform": transform,
    "test": test,
    "docs": docs,
    "all": run_all,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Steps: " + ", ".join(STEPS),
    )
    parser.add_argument("steps", nargs="*", choices=STEPS, metavar="step")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="pipeline settings (default: config/pipeline.yml)",
    )
    parser.add_argument("--target", default="dev", help="dbt target in dbt/profiles.yml")
    parser.add_argument(
        "--force", action="store_true", help="all: run dbt even if nothing new was loaded"
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="transform: rebuild incremental models from scratch",
    )
    args = parser.parse_args()
    args.steps = args.steps or ["all"]
    args.config = args.config.resolve()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    load_dotenv(ROOT / ".env")  # child processes (loaders, dbt) inherit these settings

    for step in args.steps:
        log.info("=== %s", step)
        started = time.perf_counter()
        try:
            RUNNERS[step](args)
        except StepFailed as failed:
            log.error("step '%s' failed: %s", step, failed)
            sys.exit(1)
        log.info("=== %s done in %.0f s", step, time.perf_counter() - started)


if __name__ == "__main__":
    main()
