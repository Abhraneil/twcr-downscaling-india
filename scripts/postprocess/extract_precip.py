#!/usr/bin/env python3
"""Daily precipitation on the IMD 0.25 deg grid for every run of an event.

    python scripts/postprocess/extract_precip.py E2_mumbai2005 --runs-root RUNS

Expected layout (created by scripts/run/*.sh):
  RUNS/wrf/<event>_<driver>/wrfout_d01_*, wrfout_d02_*
  RUNS/regcm/<event>_<driver>_12km/output/*SHF*.nc
  RUNS/regcm/<event>_<driver>_03km/output/*SHF*.nc
plus the driver precipitation in data/drivers/<event>_<driver>_precip.nc.

Each run gives data/daily/<event>/<run>.nc with variable `pr` (day, lat, lon) [mm/day]:
24 h totals for the windows score_start + n days (03 UTC to 03 UTC), on the IMD grid
cropped to the scoring box plus 0.5 deg. Missing runs are skipped with a message.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, load_config  # noqa: E402
from remap import Remapper  # noqa: E402

IMD_LAT = 6.5 + 0.25 * np.arange(129)
IMD_LON = 66.5 + 0.25 * np.arange(135)


def windows(ev):
    s = datetime.fromisoformat(ev["score_start"])
    return [(s + timedelta(days=i), s + timedelta(days=i + 1)) for i in range(ev["score_ndays"])]


def target_grid(ev, margin=0.5):
    b = ev["score_box"]
    la = IMD_LAT[(IMD_LAT >= b["lat_min"] - margin) & (IMD_LAT <= b["lat_max"] + margin)]
    lo = IMD_LON[(IMD_LON >= b["lon_min"] - margin) & (IMD_LON <= b["lon_max"] + margin)]
    return la, lo


def grid_spacing_km(lat2d, lon2d):
    la, lo = np.radians(lat2d), np.radians(lon2d)
    dy = 6371.0 * np.abs(np.diff(la, axis=0))
    dx = 6371.0 * np.abs(np.diff(lo, axis=1)) * np.cos(la[:, 1:])
    return float(np.median(np.concatenate([dy.ravel(), dx.ravel()])))


def daily_from_accum(times, acc, wins):
    """acc: accumulated mm at `times` (must contain every window edge exactly)."""
    tix = {np.datetime64(t, "s"): i for i, t in enumerate(times.astype("datetime64[s]"))}
    out = []
    for s, e in wins:
        i0, i1 = tix.get(np.datetime64(s, "s")), tix.get(np.datetime64(e, "s"))
        if i0 is None or i1 is None:
            raise KeyError(f"output lacks window edge {s} or {e}")
        out.append(acc[i1] - acc[i0])
    return np.stack(out)


def daily_from_rate(times, rate, interval_h, wins):
    """rate [kg m-2 s-1] at `times`, each value the mean over the interval ending at t."""
    t = times.astype("datetime64[s]")
    out = []
    for s, e in wins:
        sel = (t > np.datetime64(s, "s")) & (t <= np.datetime64(e, "s"))
        n = int(sel.sum())
        if n * interval_h != 24:
            raise ValueError(f"window {s}: {n} values x {interval_h} h != 24 h")
        out.append(rate[sel].sum(axis=0) * interval_h * 3600.0)
    return np.stack(out)


def wrf_daily(files, wins):
    ds = xr.open_mfdataset(sorted(files), combine="nested", concat_dim="Time", decode_times=False)
    def _txt(x):   # Times is char(Time, DateStrLen); xarray may or may not join the characters
        x = x if isinstance(x, (bytes, str)) else b"".join(np.atleast_1d(x))
        return x.decode() if isinstance(x, bytes) else x
    times = np.array([datetime.strptime(_txt(x), "%Y-%m-%d_%H:%M:%S") for x in ds["Times"].values],
                     dtype="datetime64[s]")
    acc = ds["RAINC"].values + ds["RAINNC"].values
    if "RAINSH" in ds:
        acc = acc + ds["RAINSH"].values
    lat, lon = ds["XLAT"].values[0], ds["XLONG"].values[0]
    return daily_from_accum(times, acc, wins), lat, lon, float(ds.attrs["DX"]) / 1000.0


def regcm_daily(files, wins):
    ds = xr.open_mfdataset(sorted(files), combine="by_coords")
    rate = ds["pr"].values
    times = ds["time"].values
    lat, lon = ds["xlat"].values, ds["xlon"].values
    step = np.diff(times.astype("datetime64[s]")).astype(int)
    if not np.all(step == 3600):
        raise ValueError("RegCM SHF output must be hourly")
    return daily_from_rate(times, rate, 1, wins), lat, lon, grid_spacing_km(lat, lon)


def driver_daily(f, wins):
    ds = xr.open_dataset(f)
    lat1, lon1 = ds["lat"].values, ds["lon"].values
    lon2, lat2 = np.meshgrid(lon1, lat1)
    pr = ds["pr"].values
    return daily_from_rate(ds["time"].values, pr, int(ds.attrs["interval_hours"]), wins), lat2, lon2, \
        grid_spacing_km(lat2, lon2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("event")
    ap.add_argument("--runs-root", type=Path, required=True)
    a = ap.parse_args()
    cfg = load_config()
    ev = cfg["events"][a.event]
    wins = windows(ev)
    tla, tlo = target_grid(ev)
    outdir = DATA / "daily" / a.event
    outdir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for drv in ev["drivers"]:
        w = a.runs_root / "wrf" / f"{a.event}_{drv}"
        jobs.append((f"WRF_12km_{drv}", wrf_daily, list(w.glob("wrfout_d01_*"))))
        jobs.append((f"WRF_3km_{drv}", wrf_daily, list(w.glob("wrfout_d02_*"))))
        for res, tag in (("12km", "12km"), ("03km", "3km")):
            r = a.runs_root / "regcm" / f"{a.event}_{drv}_{res}" / "output"
            jobs.append((f"RegCM_{tag}_{drv}", regcm_daily, list(r.glob("*SHF*.nc"))))
        f = DATA / "drivers" / f"{a.event}_{drv}_precip.nc"
        jobs.append((f"DRIVER_{drv}", driver_daily, f if f.exists() else None))
    for name, fn, src in jobs:
        if not src:
            print(f"skip {name}: no output found")
            continue
        daily, lat, lon, dx = fn(src, wins)
        rm = Remapper(lat, lon, tla, tlo, src_dx_km=dx)
        field = np.stack([rm(d) for d in daily])
        da = xr.DataArray(field.astype("float32"), dims=("day", "lat", "lon"),
                          coords={"day": np.array([s for s, _ in wins], dtype="datetime64[s]"),
                                  "lat": tla, "lon": tlo},
                          name="pr", attrs={"units": "mm/day", "window": "24 h from the 'day' time (03 UTC)",
                                            "source_dx_km": dx, "remap_subsamples": rm.k})
        da.to_netcdf(outdir / f"{name}.nc")
        print(f"{name}: dx={dx:.1f} km, k={rm.k}, box max {np.nanmax(field):.0f} mm/day")


if __name__ == "__main__":
    main()
