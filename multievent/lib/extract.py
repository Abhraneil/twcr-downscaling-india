#!/usr/bin/env python3
"""Daily rain on the IMD 0.25 deg grid for every finished case, and for its driver (step 13).

    python multievent/lib/extract.py [--force]

For each case with timing.txt: the 24 h windows of its case.json (03 UTC to 03 UTC, the event's
IMD days plus the margin days), from the d02 (12 km) wrfout files, remapped conservatively onto
the IMD cells of the event box plus 1 deg (scripts/postprocess/extract_precip.py, remap.py).
For each event x driver: the driver's own rain on the same cells and windows (added value).
Writes $TWCR_DATA/daily/<case>.nc and $TWCR_DATA/daily/DRIVER_<event>_<driver>.nc.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import xarray as xr

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "postprocess"))
from common import DATA, driver_file  # noqa: E402
from extract_precip import IMD_LAT, IMD_LON, driver_daily, wrf_daily  # noqa: E402
from remap import Remapper  # noqa: E402

HALF_BOX = 0.625 + 1.0          # 5 x 5 IMD cells around the box centre, plus 1 deg


def target(ev):
    la = IMD_LAT[np.abs(IMD_LAT - ev["lat"]) <= HALF_BOX + 1e-6]
    lo = IMD_LON[np.abs(IMD_LON - ev["lon"]) <= HALF_BOX + 1e-6]
    return la, lo


def windows(c):
    s = datetime.fromisoformat(c["dates"]["score_start"])
    return [(s + timedelta(days=k), s + timedelta(days=k + 1)) for k in range(c["dates"]["score_ndays"])]


def save(field, wins, la, lo, f, attrs):
    f.parent.mkdir(parents=True, exist_ok=True)
    xr.DataArray(field.astype("float32"), dims=("day", "lat", "lon"),
                 coords={"day": np.array([s for s, _ in wins], dtype="datetime64[s]"), "lat": la, "lon": lo},
                 name="pr", attrs=dict(units="mm/day", window="24 h from the 'day' time (03 UTC)", **attrs)).to_netcdf(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    runs = Path(os.environ.get("ME_RUNS", Path.home() / "multievent" / "runs"))
    out = DATA / "daily"
    done_drivers = set()
    n = 0
    for d in sorted((runs / "cases").glob("*")):
        if not (d / "timing.txt").exists():
            continue
        c = json.loads((d / "case.json").read_text())
        ev = c["event_info"]
        wins = windows(c)
        la, lo = target(ev)
        f = out / f"{c['case']}.nc"
        if a.force or not f.exists():
            daily, lat, lon, dx = wrf_daily(sorted(d.glob("wrfout_d02_*")), wins)
            rm = Remapper(lat, lon, la, lo, src_dx_km=dx)
            save(np.stack([rm(x) for x in daily]), wins, la, lo, f,
                 dict(case=c["case"], event=c["event"], driver=c["driver"], physics=c["physics_id"], source_dx_km=dx))
            n += 1
            print(f"{c['case']}: max {np.nanmax(daily):.0f} mm/day on the model grid")
        key = (c["event"], c["driver"])
        g = out / f"DRIVER_{c['event']}_{c['driver']}.nc"
        if key not in done_drivers and (a.force or not g.exists()):
            pf = driver_file(c["event"], c["driver"]).with_name(f"{c['event']}_{c['driver']}_precip.nc")
            daily, lat, lon, dx = driver_daily(pf, wins)
            rm = Remapper(lat, lon, la, lo, src_dx_km=dx)
            save(np.stack([rm(x) for x in daily]), wins, la, lo, g, dict(event=c["event"], driver=c["driver"], source_dx_km=dx))
        done_drivers.add(key)
    print(f"{n} cases extracted to {out}")


if __name__ == "__main__":
    main()
