"""Publish the Parquet export as a GitHub release, for the deployed app to download.

One release per data refresh, tagged by the newest month in the data (data-2026-09).
The files sit next to the repository, not in its history, so refreshes don't make
the repository grow. The deployed app reads the newest release through an address
that always points to it:
    TEMPRADAR_PARQUET = "https://github.com/<owner>/<repo>/releases/latest/download"
and downloads the files when it starts (reboot the app after publishing).

Needs the GitHub CLI (gh), signed in: gh auth login. Run after the export, from
the project folder:
    python export/publish_release.py --dry-run   # show what would be published
    python export/publish_release.py
Publishing the same data again replaces the files of that release.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

# The list of files the app downloads, so both sides agree on it
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from data import all_parquet_files  # noqa: E402

log = logging.getLogger("publish")


def run(command: list[str], dry_run: bool) -> None:
    log.info("%s", " ".join(command[:6]) + (" ..." if len(command) > 6 else ""))
    if not dry_run:
        subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folder", type=Path, default=Path("data/app"))
    parser.add_argument("--dry-run", action="store_true", help="only show what would happen")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if shutil.which("gh") is None:
        sys.exit("The GitHub CLI (gh) isn't installed: https://cli.github.com, then gh auth login")

    files = [args.folder / name for name in all_parquet_files()]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        sys.exit(f"Not in {args.folder}: {', '.join(missing)}. Run: python pipeline.py export")

    meta = json.loads((args.folder / "metadata.json").read_text(encoding="utf-8"))
    until = date.fromisoformat(meta["data_until"])
    tag = f"data-{until:%Y-%m}"
    size = sum(f.stat().st_size for f in files) / 1e6
    month = f"{until:%b %Y}"
    log.info("%d files, %.0f MB, data until %s: release %s", len(files), size, month, tag)

    exists = subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0
    paths = [str(f) for f in files]
    if exists:
        # The same data again: replace the release's files
        run(["gh", "release", "upload", tag, *paths, "--clobber"], args.dry_run)
    else:
        notes = (
            f"Parquet export for the Euro Warming Monitor app: {meta['study_area']}, "
            f"ERA5 data until {until:%B %Y}, exported {meta['exported_at']}."
        )
        title = f"Data until {until:%B %Y}"
        options = ["--title", title, "--notes", notes, "--latest"]
        run(["gh", "release", "create", tag, *paths, *options], args.dry_run)
    log.info("done%s", " (dry run: nothing published)" if args.dry_run else "")


if __name__ == "__main__":
    main()
