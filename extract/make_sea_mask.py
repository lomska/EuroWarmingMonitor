"""Make the map's sea mask: the sea and large lakes over the study area, as GeoJSON.

The app draws it over the coloured grid cells, so the colours stop at the coast.
The outlines are Natural Earth's 1:50m ocean and lakes (public domain), clipped to
the study area and simplified with PostGIS (the database must be running; any role
will do, nothing is written to it). The result, app/sea.geojson (about 130 KB for
Europe), is part of the repository, so this only needs running again after changing
the study area.

Usage (from the project folder, with .venv active and the database running):
    python extract/make_sea_mask.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import urllib.request
from pathlib import Path

import psycopg
import yaml
from dotenv import load_dotenv

log = logging.getLogger("extract")

NATURAL_EARTH = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
LAYERS = ["ne_50m_ocean.geojson", "ne_50m_lakes.geojson"]
PAD = 0.125  # degrees: the outer cells reach half a cell beyond the study area
SIMPLIFY = 0.01  # degrees (about 1 km): far finer than a 28 km cell
DECIMALS = 3  # coordinate decimals in the output

# One multipolygon of all the water inside the box, simplified
CLIP_SQL = """
    with water as (
        select st_makevalid(st_geomfromgeojson(g)) as geom
        from unnest(%(geoms)s::text[]) as g
    ),
    box as (
        select st_makeenvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326) as geom
    )
    select st_asgeojson(
        st_simplifypreservetopology(
            st_collectionextract(st_intersection(st_union(water.geom), box.geom), 3),
            %(tolerance)s
        ),
        %(decimals)s
    )
    from water, box
    group by box.geom
"""


def connect() -> psycopg.Connection:
    """Connect as the read-only reader role: the clipping only reads."""
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user="reader",
        password=os.environ["READER_PASSWORD"],
        options="-c search_path=public",  # where the PostGIS functions are
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config/pipeline.yml"))
    parser.add_argument("--out", type=Path, default=Path("app/sea.geojson"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()

    north, west, south, east = yaml.safe_load(args.config.read_text(encoding="utf-8"))[
        "study_area"
    ]["area"]

    geoms = []
    for layer in LAYERS:
        log.info("downloading %s", layer)
        with urllib.request.urlopen(f"{NATURAL_EARTH}/{layer}", timeout=120) as response:
            features = json.load(response)["features"]
        geoms += [json.dumps(f["geometry"]) for f in features]

    with connect() as pg:
        geometry = pg.execute(
            CLIP_SQL,
            {
                "geoms": geoms,
                "west": west - PAD,
                "south": south - PAD,
                "east": east + PAD,
                "north": north + PAD,
                "tolerance": SIMPLIFY,
                "decimals": DECIMALS,
            },
        ).fetchone()[0]

    mask = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": json.loads(geometry)}],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(mask, separators=(",", ":")), encoding="utf-8")
    log.info("wrote %s (%.0f KB)", args.out, args.out.stat().st_size / 1e3)


if __name__ == "__main__":
    main()
