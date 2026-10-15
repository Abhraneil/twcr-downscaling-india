#!/usr/bin/env python3
"""Download IMD 0.25 deg gridded daily rainfall (Pai et al. 2014) for the event years.

    python scripts/download/get_imd.py 1924 2005

Uses the `imdlib` package, which fetches the yearly binary files from IMD Pune and
decodes them. Output: data/obs/imd_rain_<year>.nc, variable `rain` [mm/day],
NaN outside India (IMD missing value -999). The date label is IMD's; which 24 h
window it covers is set by observations.imd_label in config/experiment.yaml and
checked by scripts/scoring/check_imd_convention.py.

If the IMD server is unreachable, download Rainfall_ind<YYYY>_rfp25.grd manually from
https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html into data/raw/imd/ and
run this script again; it will read the local file.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA  # noqa: E402

NLAT, NLON = 129, 135          # 6.5-38.5N, 66.5-100.0E at 0.25 deg
LAT = 6.5 + 0.25 * np.arange(NLAT)
LON = 66.5 + 0.25 * np.arange(NLON)


def read_grd(path: Path, year: int) -> xr.DataArray:
    raw = np.fromfile(path, dtype="<f4")
    ndays = raw.size // (NLAT * NLON)
    expected = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
    if ndays != expected:
        raise ValueError(f"{path}: {ndays} days, expected {expected}")
    arr = raw.reshape(ndays, NLAT, NLON)
    arr = np.where(arr <= -998, np.nan, arr)
    t = np.arange(f"{year}-01-01", f"{year + 1}-01-01", dtype="datetime64[D]")
    return xr.DataArray(arr, dims=("time", "lat", "lon"), coords={"time": t, "lat": LAT, "lon": LON},
                        name="rain", attrs={"units": "mm/day", "source": "IMD 0.25 deg (Pai et al. 2014)"})


def main(years) -> None:
    rawdir = DATA / "raw" / "imd"
    rawdir.mkdir(parents=True, exist_ok=True)
    outdir = DATA / "obs"
    outdir.mkdir(parents=True, exist_ok=True)
    for y in map(int, years):
        local = rawdir / f"{y}.grd"
        if not local.exists():
            alt = rawdir / f"Rainfall_ind{y}_rfp25.grd"
            if alt.exists():
                local = alt
            else:
                import imdlib
                imdlib.get_data("rain", y, y, fn_format="yearwise", file_dir=str(rawdir))
                cand = list(rawdir.rglob(f"{y}.grd"))
                if not cand:
                    raise FileNotFoundError(f"imdlib did not produce {y}.grd under {rawdir}")
                local = cand[0]
        da = read_grd(local, y)
        f = outdir / f"imd_rain_{y}.nc"
        da.to_netcdf(f)
        print(f"wrote {f}; max daily value {float(da.max()):.1f} mm, valid cells {int(np.isfinite(da[0]).sum())}")


if __name__ == "__main__":
    main(sys.argv[1:])
