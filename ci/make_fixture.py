"""Write a tiny, made-up data set in the same formats as the real downloads.

It lets CI run the loaders and the whole dbt project in about a minute,
with no Copernicus account and no large downloads:
  * ERA5-style NetCDF files for 3 x 3 grid points, 1940-2025, with a seasonal
    cycle, a warming trend and random noise; the last 3 months are marked
    preliminary (ERA5T), and the south-east point is sea;
  * GeoNames-style text files with a few places, including one exactly on
    the corner of four squares (tests the tie-breaker) and one with a
    missing elevation (-9999) in a country coded "NA" (tests text parsing).

The values are realistic but not real; don't use them for anything else.

Usage (from the project folder):
    python ci/make_fixture.py [--config ci/pipeline.yml]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import yaml

STEP = 0.25


def grid(area: list[float]) -> tuple[np.ndarray, np.ndarray]:
    north, west, south, east = area
    lats = np.arange(north, south - STEP / 2, -STEP)  # north to south, as ERA5
    lons = np.arange(west, east + STEP / 2, STEP)
    return lats, lons


def temperatures(lats, lons, months: pd.DatetimeIndex) -> np.ndarray:
    """Kelvin, shape (months, lats, lons)."""
    rng = np.random.default_rng(42)
    years = months.year.to_numpy() + (months.month.to_numpy() - 1) / 12
    # about 13 °C on average, January coldest, warming 0.4 °C per decade since 1975
    season = -11 * np.cos(2 * np.pi * (months.month.to_numpy() - 1) / 12)
    trend = np.where(years > 1975, 0.04 * (years - 1975), 0.0)
    base = 286.0 + season + trend
    # colder to the north, slightly warmer to the east
    by_lat = (lats - lats.mean()) * -0.8
    by_lon = (lons - lons.mean()) * 0.3
    values = (
        base[:, None, None]
        + by_lat[None, :, None]
        + by_lon[None, None, :]
        + rng.normal(0, 1.2, (len(months), len(lats), len(lons)))
    )
    return values.astype("float32")


def write_era5(raw_dir: Path, cfg: dict) -> None:
    lats, lons = grid(cfg["study_area"]["area"])
    end = pd.Timestamp(cfg["period"]["end_month"] + "-01")
    months = pd.date_range(f"{cfg['period']['start_year']}-01-01", end, freq="MS")
    expver = np.where(months > end - pd.DateOffset(months=3), "0005", "0001")

    t2m = xr.Dataset(
        {"t2m": (("valid_time", "latitude", "longitude"), temperatures(lats, lons, months))},
        coords={
            "valid_time": months,
            "latitude": lats,
            "longitude": lons,
            "expver": ("valid_time", expver),
        },
    )
    name = f"era5_t2m_{months[0]:%Y%m}_{months[-1]:%Y%m}.nc"
    t2m.to_netcdf(raw_dir / name)

    lsm = np.ones((1, len(lats), len(lons)), dtype="float32")
    lsm[0, -1, -1] = 0.0  # one sea point
    xr.Dataset(
        {"lsm": (("valid_time", "latitude", "longitude"), lsm)},
        coords={"valid_time": [pd.Timestamp("2020-01-01")], "latitude": lats, "longitude": lons},
    ).to_netcdf(raw_dir / "era5_land_sea_mask.nc")
    print(f"wrote {name} ({len(months)} months x {len(lats)} x {len(lons)}) and the land-sea mask")


# fmt: off
# GeoNames columns, in file order (see load/load_geonames.py)
#  geonameid name asciiname alternatenames lat lon feature_class feature_code
#  country cc2 admin1 admin2 admin3 admin4 population elevation dem timezone modified
PLACES = [
    ("1", "Tbilisi", "Tbilisi", "Tiflis,Tbilisi", "41.69411", "44.83368", "P", "PPLC",
     "GE", "", "51", "", "", "", "1049498", "", "490", "Asia/Tbilisi", "2024-01-01"),
    ("2", "Rustavi", "Rustavi", "", "41.54949", "44.99323", "P", "PPLA",
     "GE", "", "73", "", "", "", "125103", "", "352", "Asia/Tbilisi", "2024-01-01"),
    ("3", "Mtskheta", "Mtskheta", "", "41.84514", "44.71875", "P", "PPLA",
     "GE", "", "69", "", "", "", "7940", "", "468", "Asia/Tbilisi", "2024-01-01"),
    # exactly on the corner of four squares: belongs to the south-western one
    ("4", "Cornerville", "Cornerville", "", "41.625", "44.625", "P", "PPL",
     "GE", "", "51", "", "", "", "1500", "", "500", "Asia/Tbilisi", "2024-01-01"),
    # country code "NA" must stay text, -9999 means no elevation data
    ("5", "Nowhere", "Nowhere", "", "41.9", "44.95", "P", "PPL",
     "NA", "", "", "", "", "", "1200", "", "-9999", "Africa/Windhoek", "2024-01-01"),
]

ADMIN1 = [
    ("GE.51", "Tbilisi", "Tbilisi", "611717"),
    ("GE.69", "Mtskheta-Mtianeti", "Mtskheta-Mtianeti", "865539"),
    ("GE.73", "Kvemo Kartli", "Kvemo Kartli", "865543"),
]

COUNTRIES = [
    ("GE", "GEO", "268", "GG", "Georgia", "Tbilisi", "69700", "3731000", "AS", ".ge",
     "GEL", "Lari", "995", "####", "^(\\d{4})$", "ka,ru,hy,az", "614540", "AM,AZ,TR,RU", ""),
    ("NA", "NAM", "516", "WA", "Namibia", "Windhoek", "825418", "2448255", "AF", ".na",
     "NAD", "Dollar", "264", "", "", "en-NA,af,de", "3355338", "ZA,BW,ZM,AO", ""),
]
# fmt: on


def write_tsv(path: Path, rows, header: str | None = None) -> None:
    lines = [header] if header else []
    lines += ["\t".join(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_geonames(geo_dir: Path) -> None:
    write_tsv(geo_dir / "cities1000.txt", PLACES)
    write_tsv(geo_dir / "admin1CodesASCII.txt", ADMIN1)
    write_tsv(geo_dir / "countryInfo.txt", COUNTRIES, header="# made-up test file")
    print(f"wrote {len(PLACES)} places, {len(ADMIN1)} regions, {len(COUNTRIES)} countries")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("ci/pipeline.yml"))
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))

    raw_dir = Path(cfg["paths"]["raw_dir"]) / cfg["study_area"]["name"]
    geo_dir = Path(cfg["geonames"]["dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    geo_dir.mkdir(parents=True, exist_ok=True)

    write_era5(raw_dir, cfg)
    write_geonames(geo_dir)


if __name__ == "__main__":
    main()
