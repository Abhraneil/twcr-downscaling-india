from datetime import datetime, timedelta

import numpy as np
import pytest

import metrics as M
from extract_precip import daily_from_accum, daily_from_rate
from remap import Remapper

LAT = 17.0 + 0.25 * np.arange(16)
LON = 72.0 + 0.25 * np.arange(12)
MASK = np.ones((16, 12), bool)
W = M.area_weights(LAT, LON)


def blob(cy, cx, amp=200.0, s=1.5):
    y, x = np.meshgrid(np.arange(16), np.arange(12), indexing="ij")
    return amp * np.exp(-((y - cy) ** 2 + (x - cx) ** 2) / (2 * s * s))


def test_fss_perfect_and_disjoint():
    o = np.stack([blob(5, 5)])
    assert M.fss(o, o, MASK, 50.0, 1) == pytest.approx(1.0)
    far = np.stack([blob(13, 10)])
    assert M.fss(far, o, MASK, 50.0, 1) == pytest.approx(0.0)
    # skill grows with neighbourhood size for a displaced forecast
    near = np.stack([blob(7, 6)])
    f = [M.fss(near, o, MASK, 50.0, n) for n in (1, 3, 5, 9)]
    assert f[0] < f[1] < f[2] <= f[3] + 1e-9


def test_sal_identical_and_amplitude():
    o = blob(5, 5) + blob(11, 8, 120)
    s = M.sal(o, o, MASK, LAT, LON)
    assert abs(s["S"]) < 1e-12 and abs(s["A"]) < 1e-12 and abs(s["L"]) < 1e-12
    s2 = M.sal(2 * o, o, MASK, LAT, LON)
    assert s2["A"] == pytest.approx(2 / 3)          # (2-1)/(0.5*(2+1))
    assert abs(s2["S"]) < 1e-9 and abs(s2["L"]) < 1e-9   # scaling changes amplitude only


def test_bias_corr_location():
    o = np.stack([blob(5, 5), blob(6, 5)]) + 1.0
    m = 1.5 * o
    assert M.bias_pct(m, o, MASK, W) == pytest.approx(50.0)
    assert M.pattern_corr(m.sum(0), o.sum(0), MASK, W) == pytest.approx(1.0)
    d = M.max_location_error_km(blob(9, 5), blob(5, 5), MASK, LAT, LON)
    assert d == pytest.approx(4 * 0.25 * 111.19, rel=0.01)


def test_nan_inside_mask_is_an_error():
    o = np.stack([blob(5, 5)])
    m = o.copy()
    m[0, 3, 3] = np.nan
    with pytest.raises(ValueError):
        M.fss(m, o, MASK, 10.0, 3)


def test_remap_conserves_fine_to_coarse():
    # ~3 km source over 17-21N, 72-75E
    lat1 = np.arange(16.9, 21.1, 0.027)
    lon1 = np.arange(71.9, 75.1, 0.0285)
    lon2, lat2 = np.meshgrid(lon1, lat1)
    tla, tlo = 17.5 + 0.25 * np.arange(12), 72.5 + 0.25 * np.arange(9)
    rm = Remapper(lat2, lon2, tla, tlo, src_dx_km=3.0)
    # 1) the block integral of a rough (gamma noise) field is conserved
    f = np.random.default_rng(1).gamma(0.5, 40.0, lat2.shape)
    g = rm(f)
    assert np.isfinite(g).all()
    inside = (lat2 >= tla[0] - 0.125) & (lat2 < tla[-1] + 0.125) & (lon2 >= tlo[0] - 0.125) & (lon2 < tlo[-1] + 0.125)
    w_src = np.cos(np.radians(lat2[inside]))
    w_tgt = np.cos(np.radians(tla))[:, None] * np.ones(len(tlo))
    src_mean = np.sum(f[inside] * w_src) / w_src.sum()
    tgt_mean = np.sum(g * w_tgt) / w_tgt.sum()
    assert tgt_mean == pytest.approx(src_mean, rel=0.01)
    # 2) cell values of a smooth field equal the analytic cell average
    h = 100 + 50 * np.sin(np.radians(lat2) * 40) * np.cos(np.radians(lon2) * 30)
    gh = rm(h)
    fine = 100 + 50 * np.sin(np.radians(tla) * 40)[:, None] * np.cos(np.radians(tlo) * 30)[None, :]
    assert np.max(np.abs(gh - fine)) < 1.0      # cell average vs centre value of a smooth field
    assert np.allclose(rm(np.full(lat2.shape, 7.0)), 7.0)


def test_remap_coarse_to_fine_and_outside_domain():
    lat1, lon1 = np.arange(15.0, 23.0, 1.0), np.arange(70.0, 78.0, 1.0)
    lon2, lat2 = np.meshgrid(lon1, lat1)
    f = lat2 * 10 + lon2
    tla, tlo = 18.0 + 0.25 * np.arange(4), 73.0 + 0.25 * np.arange(4)
    g = Remapper(lat2, lon2, tla, tlo, src_dx_km=111.0)(f)
    assert g[0, 0] == pytest.approx(18 * 10 + 73)     # cell centred on a source centre
    out = Remapper(lat2, lon2, np.array([40.0, 40.25]), np.array([73.0, 73.25]), src_dx_km=111.0)(f)
    assert np.isnan(out).all()


def test_daily_windows_from_accumulation_and_rate():
    t0 = datetime(2005, 7, 24, 0)
    times = np.array([t0 + timedelta(hours=h) for h in range(0, 80)], dtype="datetime64[s]")
    acc = np.arange(80, dtype=float)[:, None, None] * np.ones((1, 2, 2))    # 1 mm per hour
    wins = [(datetime(2005, 7, 25, 3), datetime(2005, 7, 26, 3))]
    assert np.allclose(daily_from_accum(times, acc, wins), 24.0)
    rate = np.full((80, 2, 2), 1.0 / 3600.0)                                 # 1 mm h-1
    assert np.allclose(daily_from_rate(times, rate, 1, wins), 24.0)
    t3 = times[::3]
    assert np.allclose(daily_from_rate(t3, rate[::3], 3, wins), 24.0)
    with pytest.raises(ValueError):
        daily_from_rate(t3, rate[::3], 1, wins)


def test_regcm_shf_reader(tmp_path):
    import xarray as xr
    from extract_precip import regcm_daily
    t = np.arange("2005-07-25T01", "2005-07-26T04", dtype="datetime64[h]").astype("datetime64[ns]")
    lat = 19 + 0.03 * np.arange(3)[:, None] * np.ones((1, 4))
    lon = 73 + 0.03 * np.arange(4)[None, :] * np.ones((3, 1))
    ds = xr.Dataset({"pr": (("time", "jx", "iy"), np.full((t.size, 3, 4), 2.0 / 3600.0)),
                     "xlat": (("jx", "iy"), lat), "xlon": (("jx", "iy"), lon)}, coords={"time": t})
    ds.to_netcdf(tmp_path / "x_SHF.2005072500.nc")
    d, la, lo, dx = regcm_daily([tmp_path / "x_SHF.2005072500.nc"],
                                [(datetime(2005, 7, 25, 3), datetime(2005, 7, 26, 3))])
    assert np.allclose(d, 48.0) and 2.5 < dx < 3.5
