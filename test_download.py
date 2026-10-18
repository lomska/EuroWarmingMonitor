"""Test that the CDS API works: download ERA5 2 m temperature for the
Caucasus box (2020, all months) and print the file's structure.

"""

from pathlib import Path

import cdsapi
import xarray as xr

DATASET = "reanalysis-era5-single-levels-monthly-means"

REQUEST = {
    "product_type": ["monthly_averaged_reanalysis"],
    "variable": ["2m_temperature"],
    "year": ["2020"],
    "month": [f"{m:02d}" for m in range(1, 13)],
    "time": ["00:00"],
    "area": [48, 36, 36, 52],  # North, West, South, East
    "data_format": "netcdf",
    "download_format": "unarchived",
}

TARGET = Path("data/raw/test_era5_t2m_2020.nc")

def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)

    client = cdsapi.Client()
    client.retrieve(DATASET, REQUEST, str(TARGET))
    print(f"\nSaved {TARGET} ({TARGET.stat().st_size:,} bytes)\n")

    with xr.open_dataset(TARGET) as ds:
        print(ds)
        n_points = ds.sizes["latitude"] * ds.sizes["longitude"]
        print(f"\nGrid points: {n_points:,} (expected 3,185)")


if __name__ == "__main__":
    main()
