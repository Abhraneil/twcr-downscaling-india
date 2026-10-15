import numpy as np
import xarray as xr

from common import G, rh_from_q
from to_regcm import convert as to_regcm
from to_wps import convert as to_wps, read_intermediate


def test_wps_intermediate_roundtrip(std_driver, tmp_path):
    files = to_wps(std_driver, tmp_path, "TWCR", "synthetic")
    assert [f.name for f in files] == ["TWCR:2005-07-24_00", "TWCR:2005-07-24_03", "TWCR:2005-07-24_06"]
    recs = read_intermediate(files[1])
    # 6 fields x 4 levels + 13 surface + 8 soil
    assert len(recs) == 6 * 4 + 13 + 8
    r0 = recs[0]
    assert r0["hdate"].startswith("2005-07-24_03:00:00") and len(r0["hdate"]) == 24
    assert (r0["field"], r0["xlvl"], r0["nx"], r0["ny"]) == ("TT", 100000.0, 5, 4)
    assert r0["startloc"] == "SWCORNER" and r0["lat0"] == 10.0 and r0["lon0"] == 70.0
    assert r0["dlat"] == 1.0 and r0["dlon"] == 1.0 and not r0["wind_rel"]
    np.testing.assert_allclose(r0["slab"], std_driver["T"].isel(time=1, plev=0).values, rtol=1e-6)
    names = {(r["field"], r["xlvl"]) for r in recs}
    for need in [("PSFC", 200100.0), ("PMSL", 201300.0), ("SKINTEMP", 200100.0), ("LANDSEA", 200100.0),
                 ("SOILHGT", 200100.0), ("ST000010", 200100.0), ("SM100200", 200100.0), ("GHT", 50000.0),
                 ("RH", 85000.0), ("TT", 200100.0)]:
        assert need in names, need
    rh = next(r for r in recs if r["field"] == "RH" and r["xlvl"] == 85000.0)["slab"]
    t = std_driver["T"].isel(time=1).sel(plev=85000.0).values
    np.testing.assert_allclose(rh, rh_from_q(85000.0, t, 0.01), rtol=1e-5)


def test_rh_matches_ungrib_formula():
    # saturated air: q from e = es at 300 K, 1000 hPa gives RH = 100 %
    es = 611.2 * np.exp(17.67 * 26.85 / (300.0 - 29.65))
    q = 0.622 * es / (100000.0 - 0.378 * es)
    assert abs(rh_from_q(100000.0, 300.0, q) - 100.0) < 1e-6


def test_regcm_era5_layout(std_driver, tmp_path):
    files = to_regcm(std_driver, tmp_path)
    names = sorted(f.relative_to(tmp_path).as_posix() for f in files)
    assert names == ["ERA5/2005/geop_2005_07.nc", "ERA5/2005/qhum_2005_07.nc", "ERA5/2005/tatm_2005_07.nc",
                     "ERA5/2005/uwnd_2005_07.nc", "ERA5/2005/vwnd_2005_07.nc", "ERA5/SST/sst_2005_07.nc"]
    z = xr.open_dataset(tmp_path / "ERA5/2005/geop_2005_07.nc", decode_times=False)
    assert set(z.dims) == {"time", "level", "latitude", "longitude"}
    assert z["z"].dims == ("time", "level", "latitude", "longitude")
    assert list(z["level"].values) == [200, 500, 850, 1000]
    assert z["latitude"].values[0] > z["latitude"].values[-1]
    assert z["time"].attrs["calendar"] == "gregorian" and z["time"].attrs["units"].startswith("hours since")
    assert np.allclose(np.diff(z["time"].values), 3.0)
    expect = std_driver["Z"].isel(time=0).sel(plev=50000.0).values[::-1] * G
    np.testing.assert_allclose(z["z"].isel(time=0).sel(level=500).values, expect, rtol=1e-6)
    s = xr.open_dataset(tmp_path / "ERA5/SST/sst_2005_07.nc", decode_times=False)
    assert "sst" in s and "_FillValue" not in s["sst"].encoding or np.isnan(s["sst"].encoding.get("_FillValue", np.nan))
