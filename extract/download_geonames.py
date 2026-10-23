"""Download the GeoNames place lists used for the city search.

Files go to data/raw/geonames/ (see config/pipeline.yml). Safe to re-run:
files already on disk are skipped. GeoNames updates its dumps daily, but
place coordinates rarely change, so use --refresh only occasionally.

Usage (from the project folder, with .venv active):
    python extract/download_geonames.py
    python extract/download_geonames.py --refresh   # download again
"""

from __future__ import annotations

import argparse
import logging
import urllib.request
import zipfile
from pathlib import Path

import yaml

log = logging.getLogger("extract")

DEFAULT_CONFIG = Path("config/pipeline.yml")


def download(url: str, target: Path) -> None:
    """Download to a .part file first, then rename (no half-written files)."""
    part = target.with_name(target.name + ".part")
    part.unlink(missing_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response, part.open("wb") as f:
        while block := response.read(1024 * 1024):
            f.write(block)
    part.replace(target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--refresh", action="store_true", help="download even if files exist")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))["geonames"]
    out_dir = Path(cfg["dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in cfg["files"]:
        target = out_dir / name
        # A zip is only a means of transport: the .txt inside is what we keep
        final = target.with_suffix(".txt") if name.endswith(".zip") else target
        if final.exists() and not args.refresh:
            log.info("skip %s (already on disk)", final.name)
            continue

        log.info("downloading %s", name)
        download(f"{cfg['base_url']}/{name}", target)

        if name.endswith(".zip"):
            with zipfile.ZipFile(target) as z:
                z.extract(final.name, out_dir)
            target.unlink()
        log.info("saved %s (%s bytes)", final.name, f"{final.stat().st_size:,}")


if __name__ == "__main__":
    main()
