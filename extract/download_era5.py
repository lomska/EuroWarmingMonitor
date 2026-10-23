"""Download ERA5 monthly 2 m temperature and the land-sea mask from the
Copernicus Climate Data Store, as NetCDF files in data/raw/.

Safe to re-run: files already on disk are skipped, so a second run
downloads nothing new.

Usage (from the project folder, with .venv active):
    python extract/download_era5.py              # download what's missing
    python extract/download_era5.py --dry-run    # only show what would happen
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger("extract")

DEFAULT_CONFIG = Path("config/pipeline.yml")


@dataclass
class Chunk:
    """One download request: a run of years with the same months."""

    years: list[int]
    months: list[int]

    @property
    def filename(self) -> str:
        # e.g. era5_t2m_194001_194912.nc
        start = f"{self.years[0]}{self.months[0]:02d}"
        end = f"{self.years[-1]}{self.months[-1]:02d}"
        return f"era5_t2m_{start}_{end}.nc"


def plan_chunks(start_year: int, end_year: int, end_month: int, size: int) -> list[Chunk]:
    """Split the period into requests.

    A CDS request asks for every combination of the years and months listed,
    so a partly finished final year needs its own request with fewer months.
    Complete years are grouped into decades (1940-1949, 1950-1959, ...).
    """
    all_months = list(range(1, 13))
    last_full_year = end_year if end_month == 12 else end_year - 1

    chunks: list[Chunk] = []
    year = start_year
    while year <= last_full_year:
        decade_end = min((year // size) * size + size - 1, last_full_year)
        chunks.append(Chunk(list(range(year, decade_end + 1)), all_months))
        year = decade_end + 1

    if end_month < 12:
        chunks.append(Chunk([end_year], list(range(1, end_month + 1))))
    return chunks


def build_request(cfg: dict, years: list[int], months: list[int], variable: str) -> dict:
    """The request dictionary, in the same shape as the CDS 'Show API request code'."""
    era5 = cfg["era5"]
    request = {
        "product_type": [era5["product_type"]],
        "variable": [variable],
        "year": [str(y) for y in years],
        "month": [f"{m:02d}" for m in months],
        "time": ["00:00"],
        "area": cfg["study_area"]["area"],
        "data_format": "netcdf",
        "download_format": "unarchived",
    }
    if era5.get("grid"):
        request["grid"] = [str(g) for g in era5["grid"]]
    return request


def download(client, dataset: str, request: dict, target: Path) -> None:
    """Download to a temporary .part file, then rename it.

    If a download is interrupted, only the .part file is left behind, so the
    next run doesn't mistake a half-written file for a finished one.
    """
    part = target.with_name(target.name + ".part")
    part.unlink(missing_ok=True)
    client.retrieve(dataset, request, str(part))
    part.replace(target)


def find_stale(raw_dir: Path, planned: set[str]) -> list[Path]:
    """Files to delete: temperature files no longer in the plan (they would overlap
    the new ones after end_month moves) and leftover .part files.
    """
    stale = [p for p in raw_dir.glob("era5_t2m_*.nc") if p.name not in planned]
    stale += list(raw_dir.glob("*.part"))
    return sorted(stale)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dry-run", action="store_true", help="show the plan, download nothing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    raw_dir = Path(cfg["paths"]["raw_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)

    end_year, end_month = (int(p) for p in cfg["period"]["end_month"].split("-"))
    chunks = plan_chunks(
        cfg["period"]["start_year"], end_year, end_month, cfg["era5"]["years_per_request"]
    )

    # Every file this run should produce: temperature chunks + the land-sea mask
    lsm = cfg["land_sea_mask"]
    jobs = [
        (raw_dir / c.filename, build_request(cfg, c.years, c.months, cfg["era5"]["variable"]))
        for c in chunks
    ]
    jobs.append(
        (
            raw_dir / "era5_land_sea_mask.nc",
            build_request(cfg, [lsm["year"]], [int(lsm["month"])], lsm["variable"]),
        )
    )

    stale = find_stale(raw_dir, {path.name for path, _ in jobs})
    todo = [(path, req) for path, req in jobs if not path.exists()]
    log.info(
        "%s: %d files planned, %d already on disk, %d to download, %d outdated",
        cfg["study_area"]["name"], len(jobs), len(jobs) - len(todo), len(todo), len(stale),
    )
    if args.dry_run:
        for path in stale:
            log.info("would remove outdated %s", path.name)
        for path, req in todo:
            log.info("would download %s (%s, %d years x %d months)",
                     path.name, req["variable"][0], len(req["year"]), len(req["month"]))
        return

    for path in stale:
        path.unlink()
        log.info("removed outdated %s", path.name)

    if not todo:
        log.info("nothing to do")
        return

    import cdsapi  # imported here so --dry-run works without it

    client = cdsapi.Client()  # reads url and key from ~/.cdsapirc
    for i, (path, request) in enumerate(todo, start=1):
        log.info("[%d/%d] requesting %s", i, len(todo), path.name)
        download(client, cfg["era5"]["dataset"], request, path)
        log.info("[%d/%d] saved %s (%s bytes)", i, len(todo), path.name, f"{path.stat().st_size:,}")

    log.info("done")


if __name__ == "__main__":
    main()
