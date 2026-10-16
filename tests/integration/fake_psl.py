#!/usr/bin/env python3
"""Fake NOAA PSL 20CRv3 directory tree (same sub-directories, file names, dimension
names and orientation as the PSL THREDDS files) for testing get_20crv3.py offline.

    python tests/integration/fake_psl.py OUTDIR YEAR START END

Global 1 deg grid, lat 90 -> -90 (PSL order), lon 0 -> 359, levels in hPa, 3-hourly.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

out, year, t0, t1 = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4]
s = "SI" if year <= 1980 else "MO"
lat = np.arange(90.0, -90.1, -1.0)
lon = np.arange(0.0, 360.0, 1.0)
time = pd.date_range(t0, t1, freq="3h")
lev = np.array([1000, 975, 950, 925, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400,
                350, 300, 250, 200, 150, 100, 70, 50, 30, 20, 10, 5, 1], "f4")
LA = lat[:, None] * np.ones((1, lon.size))
land = ((LA > 8) & (LA < 35) & (lon[None, :] > 73) & (lon[None, :] < 90)).astype("f4")


def put(sub, fname, var, arr, dims, coords):
    d = out / f"{sub}{s}"
    d.mkdir(parents=True, exist_ok=True)
    xr.Dataset({var: (dims, arr.astype("f4"))}, coords=coords).to_netcdf(d / fname)


c3 = {"time": time, "level": ("level", lev, {"units": "millibar"}), "lat": lat, "lon": lon}
c2 = {"time": time, "lat": lat, "lon": lon}
nt = len(time)
tprof = (300.0 * (lev / 1000.0) ** 0.19).clip(195, None)
zprof = 7400.0 * np.log(1006.0 / lev)
put("prs", f"air.{year}.nc", "air", np.broadcast_to(tprof[None, :, None, None], (nt, 28, 181, 360)), ("time", "level", "lat", "lon"), c3)
put("prs", f"hgt.{year}.nc", "hgt", np.broadcast_to(zprof[None, :, None, None], (nt, 28, 181, 360)), ("time", "level", "lat", "lon"), c3)
put("prs", f"shum.{year}.nc", "shum", np.full((nt, 28, 181, 360), 0.008), ("time", "level", "lat", "lon"), c3)
put("prs", f"rhum.{year}.nc", "rhum", np.full((nt, 28, 181, 360), 70.0), ("time", "level", "lat", "lon"), c3)
put("prs", f"uwnd.{year}.nc", "uwnd", np.full((nt, 28, 181, 360), 8.0), ("time", "level", "lat", "lon"), c3)
put("prs", f"vwnd.{year}.nc", "vwnd", np.full((nt, 28, 181, 360), 1.0), ("time", "level", "lat", "lon"), c3)
put("2m", f"air.2m.{year}.nc", "air", np.full((nt, 181, 360), 300.0), ("time", "lat", "lon"), c2)
put("2m", f"tmax.2m.{year}.nc", "tmax", np.full((nt, 181, 360), 303.0), ("time", "lat", "lon"), c2)
put("2m", f"shum.2m.{year}.nc", "shum", np.full((nt, 181, 360), 0.018), ("time", "lat", "lon"), c2)
put("10m", f"uwnd.10m.{year}.nc", "uwnd", np.full((nt, 181, 360), 5.0), ("time", "lat", "lon"), c2)
put("10m", f"vwnd.10m.{year}.nc", "vwnd", np.full((nt, 181, 360), 1.0), ("time", "lat", "lon"), c2)
put("sfc", f"pres.sfc.{year}.nc", "pres", np.full((nt, 181, 360), 100500.0), ("time", "lat", "lon"), c2)
put("sfc", f"skt.{year}.nc", "skt", np.full((nt, 181, 360), 302.0), ("time", "lat", "lon"), c2)
put("sfc", f"icec.{year}.nc", "icec", np.where(np.abs(LA) > 70, 1.0, np.nan)[None].repeat(nt, 0), ("time", "lat", "lon"), c2)
put("sfc", f"prate.{year}.nc", "prate", np.full((nt, 181, 360), 1.0 / 3600.0), ("time", "lat", "lon"), c2)
put("sfc", f"cprat.{year}.nc", "cprat", np.full((nt, 181, 360), 0.5 / 3600.0), ("time", "lat", "lon"), c2)
put("misc", f"prmsl.{year}.nc", "prmsl", np.full((nt, 181, 360), 100800.0), ("time", "lat", "lon"), c2)
put("misc", f"pr_wtr.eatm.{year}.nc", "pr_wtr", np.full((nt, 181, 360), 50.0), ("time", "lat", "lon"), c2)
put("accums", f"weasd.{year}.nc", "weasd", np.zeros((nt, 181, 360)), ("time", "lat", "lon"), c2)
cs = {"time": time, "level": ("level", np.array([0.05, 0.25, 0.7, 1.5], "f4")), "lat": lat, "lon": lon}
ocean = np.where(land[None, None] > 0.5, 1.0, np.nan)
put("subsfc", f"tsoil.{year}.nc", "tsoil", 300.0 * ocean.repeat(nt, 0).repeat(4, 1), ("time", "level", "lat", "lon"), cs)
put("subsfc", f"soilw.{year}.nc", "soilw", 0.3 * ocean.repeat(nt, 0).repeat(4, 1), ("time", "level", "lat", "lon"), cs)
ct = {"time": pd.DatetimeIndex(["1800-01-01"]), "lat": lat, "lon": lon}
put("timeInvariant", "land.nc", "land", land[None], ("time", "lat", "lon"), ct)
put("timeInvariant", "hgt.sfc.nc", "hgt", (land * 300.0)[None], ("time", "lat", "lon"), ct)
put("timeInvariant", "land.sflx.nc", "land", land[None], ("time", "lat", "lon"), ct)
print("fake PSL tree in", out)
