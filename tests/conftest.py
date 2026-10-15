import sys
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
for p in ["scripts", "scripts/preprocess", "scripts/postprocess", "scripts/scoring"]:
    sys.path.insert(0, str(ROOT / p))


@pytest.fixture
def std_driver():
    """Small synthetic driver in the standardised format (scripts/common.py)."""
    rng = np.random.default_rng(0)
    t = np.array(["2005-07-24T00", "2005-07-24T03", "2005-07-24T06"], dtype="datetime64[ns]")
    lat = np.arange(10.0, 14.0, 1.0)
    lon = np.arange(70.0, 75.0, 1.0)
    plev = np.array([100000.0, 85000.0, 50000.0, 20000.0])
    sh3 = (len(t), len(plev), len(lat), len(lon))
    sh2 = (len(t), len(lat), len(lon))
    tprof = np.array([300.0, 290.0, 265.0, 220.0])[None, :, None, None]
    zprof = np.array([100.0, 1500.0, 5800.0, 12400.0])[None, :, None, None]
    ds = xr.Dataset(
        {
            "T": (("time", "plev", "lat", "lon"), (tprof + rng.normal(0, 1, sh3)).astype("f4")),
            "Z": (("time", "plev", "lat", "lon"), (zprof + rng.normal(0, 5, sh3)).astype("f4")),
            "Q": (("time", "plev", "lat", "lon"), np.full(sh3, 0.01, "f4")),
            "U": (("time", "plev", "lat", "lon"), rng.normal(5, 2, sh3).astype("f4")),
            "V": (("time", "plev", "lat", "lon"), rng.normal(0, 2, sh3).astype("f4")),
            "PSFC": (("time", "lat", "lon"), np.full(sh2, 100500.0, "f4")),
            "PMSL": (("time", "lat", "lon"), np.full(sh2, 100800.0, "f4")),
            "T2": (("time", "lat", "lon"), np.full(sh2, 301.0, "f4")),
            "Q2": (("time", "lat", "lon"), np.full(sh2, 0.018, "f4")),
            "U10": (("time", "lat", "lon"), np.full(sh2, 4.0, "f4")),
            "V10": (("time", "lat", "lon"), np.full(sh2, -1.0, "f4")),
            "SKT": (("time", "lat", "lon"), np.full(sh2, 302.0, "f4")),
            "SST": (("time", "lat", "lon"), np.full(sh2, 302.0, "f4")),
            "SEAICE": (("time", "lat", "lon"), np.zeros(sh2, "f4")),
            "SNOW": (("time", "lat", "lon"), np.zeros(sh2, "f4")),
            "ST": (("time", "soil_layer", "lat", "lon"), np.full((3, 4, 4, 5), 298.0, "f4")),
            "SM": (("time", "soil_layer", "lat", "lon"), np.full((3, 4, 4, 5), 0.3, "f4")),
            "LANDSEA": (("lat", "lon"), (np.arange(20).reshape(4, 5) % 2).astype("f4")),
            "SOILHGT": (("lat", "lon"), np.full((4, 5), 50.0, "f4")),
        },
        coords={"time": t, "plev": plev, "lat": lat, "lon": lon, "soil_layer": np.arange(4),
                "soil_top": ("soil_layer", [0, 10, 40, 100]), "soil_bot": ("soil_layer", [10, 40, 100, 200])},
        attrs={"source": "synthetic"},
    )
    return ds
