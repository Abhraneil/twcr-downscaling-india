#!/usr/bin/env python3
"""Decide from the data which 24 h window an IMD date label covers.

    python scripts/scoring/check_imd_convention.py

Anchor: the Mumbai record (944 mm at Santacruz) fell during the afternoon and night
of 26 July 2005 IST and was reported at the 08:30 IST observation on 27 July.
  label 2005-07-26 holds the maximum -> label D covers 03Z D to 03Z D+1 ('forward')
  label 2005-07-27 holds the maximum -> label D covers 03Z D-1 to 03Z D ('backward')
Exits non-zero if the data disagree with observations.imd_label in the config.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA, load_config  # noqa: E402

BOX = dict(lat=slice(18.75, 19.5), lon=slice(72.75, 73.25))   # Mumbai and Thane, IMD land cells


def main() -> int:
    cfg = load_config()
    f = DATA / "obs" / "imd_rain_2005.nc"
    if not f.exists():
        print(f"{f} missing: run scripts/download/get_imd.py 1924 2005 first")
        return 3
    da = xr.open_dataset(f)["rain"].sel(**BOX)
    days = ["2005-07-25", "2005-07-26", "2005-07-27", "2005-07-28"]
    vals = {d: float(da.sel(time=d).max()) for d in days}
    for d, v in vals.items():
        print(f"IMD {d}: box max {v:6.1f} mm")
    top = max(vals, key=vals.get)
    found = {"2005-07-26": "forward", "2005-07-27": "backward"}.get(top)
    if found is None:
        print(f"maximum on {top}: neither convention fits; inspect the data")
        return 2
    cfgv = cfg["observations"]["imd_label"]
    print(f"data imply imd_label = '{found}'; config has '{cfgv}'")
    return 0 if found == cfgv else 1


if __name__ == "__main__":
    sys.exit(main())
