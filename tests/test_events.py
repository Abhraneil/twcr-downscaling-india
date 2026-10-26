"""The objective event selection (scripts/events/select_events.py) on synthetic IMD years."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts" / "events"))
import select_events as S  # noqa: E402

LAT = 6.5 + 0.25 * np.arange(129)
LON = 66.5 + 0.25 * np.arange(135)


def write_years(d: Path, storms):
    """Dry years with planted storms: (year, day of year, lat, lon, mm/day for 3 days, radius deg)."""
    la, lo = np.meshgrid(LAT, LON, indexing="ij")
    land = (lo > 72.0) & (la < 35.0) & ~((la < 21.5) & (lo < np.interp(la, *zip(*S.WEST_COAST))))
    for y in sorted({s[0] for s in storms} | {1938, 1939, 1940, 1941}):
        t = np.arange(f"{y}-01-01", f"{y + 1}-01-01", dtype="datetime64[D]")
        r = np.full((t.size, 129, 135), 1.0, "f4")
        for (yy, doy, p, q, mm, rad) in storms:
            if yy == y:
                r[doy:doy + 3] += (mm * np.exp(-((la - p) ** 2 + (lo - q) ** 2) / rad ** 2)).astype("f4")
        r[:, ~land] = np.nan
        xr.DataArray(r, dims=("time", "lat", "lon"), coords={"time": t, "lat": LAT, "lon": LON},
                     name="rain").to_netcdf(d / f"imd_rain_{y}.nc")


def test_regions():
    assert S.region(10.0, 76.5) == "West coast and Ghats"      # Kerala, near the Ghats
    assert S.region(10.09, 77.06) == "West coast and Ghats"    # Munnar, on the crest
    assert S.region(17.92, 73.66) == "West coast and Ghats"    # Mahabaleshwar, on the crest
    assert S.region(19.1, 72.9) == "West coast and Ghats"      # Mumbai
    assert S.region(13.1, 80.3) == "Central and south"         # Chennai
    assert S.region(30.7, 79.1) == "North and northwest"       # Kedarnath
    assert S.region(25.6, 85.1) == "East"                      # Patna
    assert S.region(25.6, 91.9) == "Northeast"                 # Shillong
    assert S.region(18.5, 73.9) == "Central and south"         # Pune, east of the Ghats band


def test_selection_finds_planted_storms_and_declusters(tmp_path):
    storms = [(1938, 200, 10.0, 76.3, 200.0, 0.6),   # west coast, era A, largest
              (1938, 203, 10.5, 76.6, 120.0, 0.6),   # same storm 3 days / ~60 km later: not a second event
              (1939, 180, 15.0, 74.6, 150.0, 0.6),   # west coast, era A, second
              (1939, 250, 25.6, 85.1, 160.0, 0.8),   # east, era A
              (1940, 200, 19.0, 73.2, 180.0, 0.5),   # west coast, era B
              (1941, 220, 30.0, 78.0, 140.0, 0.8),   # north, era B
              (1941, 363, 20.0, 80.0, 100.0, 0.8)]   # central, era B, 30 Dec: window runs into 1942
    write_years(tmp_path, storms)
    out = tmp_path / "out"
    S.main(["--first", "1938", "--last", "1941", "--obs", str(tmp_path), "--out", str(out),
            "--eras", "A:1938:1939,B:1940:1941"])
    sel = pd.read_csv(out / "selected.csv", parse_dates=["first_label"])
    wc_a = sel[(sel.era == "A") & (sel.region == "West coast and Ghats")].sort_values("rank_in_stratum")
    assert list(wc_a.first_label.dt.year) == [1938, 1939]     # the 3-days-later echo is not counted
    assert abs(wc_a.iloc[0].lat - 10.0) <= 0.5 and wc_a.iloc[0].first_label.dayofyear == 201
    assert ((sel.era == "A") & (sel.region == "East") & (sel.first_label.dt.year == 1939)).any()
    assert ((sel.era == "B") & (sel.region == "North and northwest") & (sel.first_label.dt.year == 1941)).any()
    # a 200 mm/day Gaussian storm of radius 0.6 deg: the 5x5-cell box mean is 0.5-0.7 of its peak
    top = wc_a.iloc[0]
    assert 300 < top.box_mm < 430 and 590 < top.peak_cell_3day_mm < 610
    assert (out / "SELECTED.md").exists() and (out / "candidates.csv").exists()
