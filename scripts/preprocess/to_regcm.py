#!/usr/bin/env python3
"""Write RegCM5 ICBC input files from a standardised driver file.

    python scripts/preprocess/to_regcm.py E1_kerala1924 20CRv3 DRIVER_DIR

RegCM5 has no 20CRv3 reader, so both drivers are written in the layout of the
RegCM5 ERA5 netCDF reader (PreProc/ICBC/mod_era5.F90, dattyp='ERA5') and SST
reader (mod_sst_gnhnc.F90, ssttyp='ERA5'):

  DRIVER_DIR/<driver>/ERA5/YYYY/{tatm,geop,qhum,uwnd,vwnd}_YYYY_MM.nc
        variables t [K], z [m2 s-2], q [kg kg-1], u, v [m s-1]
        dims (time, level, latitude, longitude); 'time' has units + calendar
  DRIVER_DIR/<driver>/ERA5/SST/sst_YYYY_MM.nc     variable sst [K]

The reader takes time index = (date - first time in file) / ibdyfrq + 1, so the
files hold a regular 3-hourly series and the namelists use ibdyfrq = 3.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import G, check_standard, driver_file  # noqa: E402

FILES = [("tatm", "t", "T", 1.0, "K"), ("geop", "z", "Z", G, "m**2 s**-2"),
         ("qhum", "q", "Q", 1.0, "kg kg**-1"), ("uwnd", "u", "U", 1.0, "m s**-1"),
         ("vwnd", "v", "V", 1.0, "m s**-1")]
TIME_UNITS = "hours since 1900-01-01 00:00:00"


def _encode_time(times):
    hrs = (times - np.datetime64("1900-01-01T00:00:00")) / np.timedelta64(1, "h")
    return xr.DataArray(hrs.astype("float64"), dims="time",
                        attrs={"units": TIME_UNITS, "calendar": "gregorian", "long_name": "time"})


def convert(ds: xr.Dataset, root: Path) -> list[Path]:
    check_standard(ds)
    t = ds["time"].values
    years_months = {(int(str(x)[:4]), int(str(x)[5:7])) for x in t}
    written = []
    for (yy, mm) in sorted(years_months):
        sel = np.array([(int(str(x)[:4]), int(str(x)[5:7])) == (yy, mm) for x in t])
        sub = ds.isel(time=sel)
        # ERA5 conventions: latitude north->south, levels top->bottom (hPa)
        sub = sub.sortby("lat", ascending=False).sortby("plev", ascending=True)
        coords = {"latitude": ("latitude", sub["lat"].values.astype("float32"),
                               {"units": "degrees_north"}),
                  "longitude": ("longitude", sub["lon"].values.astype("float32"),
                                {"units": "degrees_east"}),
                  "level": ("level", (sub["plev"].values / 100.0).astype("int32"),
                            {"units": "millibars"})}
        d = root / "ERA5" / f"{yy:04d}"
        d.mkdir(parents=True, exist_ok=True)
        for fname, vname, std, scale, units in FILES:
            arr = (sub[std].values * scale).astype("float32")
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"{std} has non-finite values")
            out = xr.Dataset({vname: (("time", "level", "latitude", "longitude"), arr, {"units": units})},
                             coords=coords)
            out["time"] = _encode_time(sub["time"].values)
            f = d / f"{fname}_{yy:04d}_{mm:02d}.nc"
            out.to_netcdf(f, encoding={"time": {"dtype": "float64"}, vname: {"_FillValue": None}})
            written.append(f)
        sst = sub["SST"].values.astype("float32")
        if not np.all(np.isfinite(sst)):
            raise ValueError("SST has non-finite values")
        out = xr.Dataset({"sst": (("time", "latitude", "longitude"), sst, {"units": "K"})},
                         coords={k: v for k, v in coords.items() if k != "level"})
        out["time"] = _encode_time(sub["time"].values)
        dsst = root / "ERA5" / "SST"
        dsst.mkdir(parents=True, exist_ok=True)
        f = dsst / f"sst_{yy:04d}_{mm:02d}.nc"
        out.to_netcdf(f, encoding={"time": {"dtype": "float64"}, "sst": {"_FillValue": None}})
        written.append(f)
    return written


def main(event: str, driver: str, outroot: str) -> None:
    ds = xr.open_dataset(driver_file(event, driver))
    files = convert(ds, Path(outroot) / driver)
    print("\n".join(str(f) for f in files))


if __name__ == "__main__":
    main(*sys.argv[1:4])
