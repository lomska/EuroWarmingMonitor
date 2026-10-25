"""Smoke test: run the app headless on both data sources and fail on any error.

Needs the database with the CI data, and the Parquet export in data/app/.
Usage (from the project folder):
    python ci/check_app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

APP_DIR = Path(__file__).resolve().parents[1] / "app"
APP = str(APP_DIR / "streamlit_app.py")
sys.path.insert(0, str(APP_DIR))  # the app's data module, to look up a test cell

from data import open_source  # noqa: E402

# A grid cell with no town in it, whatever the data (the CI test area or all of Europe)
CELL_WITHOUT_TOWN = """
    select grid_point_id from dim_grid_point as g
    where not exists (select 1 from dim_city as c where c.grid_point_id = g.grid_point_id)
    order by grid_point_id
    limit 1
"""


def shown(at: AppTest) -> str:
    """The title naming the chosen place or grid cell."""
    return at.subheader[0].value if at.subheader else ""


def check(source: str) -> list[str]:
    os.environ["TEMPRADAR_SOURCE"] = source
    st.cache_resource.clear()  # the open data source is cached
    st.cache_data.clear()
    problems = []

    at = AppTest.from_file(APP, default_timeout=60).run()
    problems += [e.value for e in at.exception]
    if not shown(at):
        problems.append("no place shown on the start page")

    # A misspelt search should still find the place and show it
    at.text_input[0].input("Tbilsi").run()
    problems += [e.value for e in at.exception]
    if not shown(at).startswith("Tbilisi"):
        problems.append(f"search for 'Tbilsi' showed {shown(at)[:60]}")

    # The whole year compared with 1961-1990, then a single month
    at.segmented_control[0].set_value("Year").run()
    at.segmented_control[1].set_value("1961–1990").run()
    problems += [e.value for e in at.exception]
    at.segmented_control[0].set_value("Jan").run()
    problems += [e.value for e in at.exception]
    if not any("January" in m.value for m in at.markdown):
        problems.append("no January numbers after choosing Jan")

    # A link to a grid cell without a town (what a click on the map leads to)
    cell = open_source().query(CELL_WITHOUT_TOWN)["grid_point_id"].iloc[0]
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["cell"] = cell
    at.run()
    problems += [e.value for e in at.exception]
    if shown(at) != "A grid cell with no towns":
        problems.append(f"cell without a town showed {shown(at)[:60]}")
    return [f"{source}: {p}" for p in problems]


def main() -> None:
    load_dotenv(".env")
    problems = check("postgres") + check("parquet")
    for p in problems:
        print("FAIL", p)
    if problems:
        sys.exit(1)
    print("app OK on postgres and parquet")


if __name__ == "__main__":
    main()
