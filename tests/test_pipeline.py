"""End-to-end smoke test: fake WRF output -> daily IMD-grid fields -> scores -> figures.

The fake WRF run rains exactly the observed field, so its scores must be perfect;
a second fake run rains the same field shifted by 0.5 deg and must score worse.
"""
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
import xarray as xr

import extract_precip as EP
import plot_event as PE
import score_all as SA
import check_imd_convention as CIC

EV = "E2_mumbai2005"


def truth(lat, lon, shift=0.0, day=0):
    amp = [80.0, 400.0, 150.0, 60.0][day]
    return amp * np.exp(-(((lat - 19.1) / 0.4) ** 2 + ((lon - 73.0 - shift) / 0.3) ** 2))


def fake_wrfout(path, shift):
    lat1 = np.arange(15.7, 22.1, 0.027)
    lon1 = np.arange(70.2, 76.9, 0.0285)
    lon2, lat2 = np.meshgrid(lon1, lat1)
    t0 = datetime(2005, 7, 24, 0)
    nt = 126
    times = [t0 + timedelta(hours=h) for h in range(nt)]
    s = datetime(2005, 7, 25, 3)
    acc = np.zeros((nt,) + lat2.shape)
    for i, t in enumerate(times[1:], 1):
        k = int((t - s).total_seconds() // 86400) if t > s else -1
        rate = truth(lat2, lon2, shift, k) / 24.0 if 0 <= k < 4 else 0.0
        acc[i] = acc[i - 1] + rate
    ds = xr.Dataset(
        {"Times": (("Time",), np.array([t.strftime("%Y-%m-%d_%H:%M:%S").encode() for t in times], dtype="S19")),
         "RAINC": (("Time", "south_north", "west_east"), 0.3 * acc.astype("f4")),
         "RAINNC": (("Time", "south_north", "west_east"), 0.7 * acc.astype("f4")),
         "XLAT": (("Time", "south_north", "west_east"), np.repeat(lat2[None], nt, 0).astype("f4")),
         "XLONG": (("Time", "south_north", "west_east"), np.repeat(lon2[None], nt, 0).astype("f4"))},
        attrs={"DX": 3000.0})
    ds["Times"] = ds["Times"].astype("S19")
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    data = tmp_path / "data"
    for mod in (EP, SA, PE, CIC):
        monkeypatch.setattr(mod, "DATA", data)
    for mod in (SA, PE):
        monkeypatch.setattr(mod, "ROOT", tmp_path)
    # IMD file for 2005 (backward labels: label D = 03Z D-1 -> 03Z D, as in the real data)
    lat, lon = 6.5 + 0.25 * np.arange(129), 66.5 + 0.25 * np.arange(135)
    t = np.arange("2005-01-01", "2006-01-01", dtype="datetime64[D]")
    rain = np.zeros((t.size, 129, 135), "f4")
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    for k in range(4):
        idx = int((np.datetime64("2005-07-26") - t[0]).astype(int)) + k
        rain[idx] = truth(LA, LO, 0.0, k)
    rain[:, LO < 72.6] = np.nan              # the sea is missing in IMD
    (data / "obs").mkdir(parents=True)
    xr.DataArray(rain, dims=("time", "lat", "lon"), coords={"time": t, "lat": lat, "lon": lon},
                 name="rain").to_netcdf(data / "obs" / "imd_rain_2005.nc")
    runs = tmp_path / "runs"
    fake_wrfout(runs / "wrf" / f"{EV}_ERA5" / "wrfout_d02_2005-07-24_00:00:00", 0.0)
    fake_wrfout(runs / "wrf" / f"{EV}_20CRv3" / "wrfout_d02_2005-07-24_00:00:00", 0.5)
    return tmp_path, runs


def test_pipeline_end_to_end(sandbox, monkeypatch):
    root, runs = sandbox
    monkeypatch.setattr(sys, "argv", ["extract_precip.py", EV, "--runs-root", str(runs)])
    EP.main()
    assert (root / "data/daily" / EV / "WRF_3km_ERA5.nc").exists()
    cfg = SA.load_config()
    cfg["events"] = {EV: cfg["events"][EV]}
    monkeypatch.setattr(SA, "load_config", lambda: cfg)
    monkeypatch.setattr(PE, "load_config", lambda: cfg)
    SA.main()
    df = pd.read_csv(root / "results" / "scores.csv")
    get = lambda run, m: float(df[(df.run == run) & (df.metric == m)].value.iloc[0])
    assert abs(get("WRF_3km_ERA5", "bias_pct")) < 2.0
    assert get("WRF_3km_ERA5", "corr_total") > 0.99
    assert get("WRF_3km_ERA5", "FSS_115.6mm_1pt") > 0.95
    assert get("WRF_3km_ERA5", "maxloc_err_km") < 30
    assert get("WRF_3km_20CRv3", "FSS_115.6mm_1pt") < get("WRF_3km_ERA5", "FSS_115.6mm_1pt")
    assert get("WRF_3km_20CRv3", "maxloc_err_km") > 40
    assert (root / "results" / "SCORECARD.md").exists()
    hyp = (root / "results" / "HYPOTHESES.md").read_text()
    assert "| H1 | WRF_3km_ERA5 |" in hyp and "PASS" in hyp
    PE.main()
    assert (root / "results" / "figures" / f"{EV}_totals.png").exists()
    assert (root / "results" / "figures" / f"{EV}_fss.png").exists()
