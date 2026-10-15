"""Shared helpers: configuration, the standardised driver format, thermodynamics."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Spatial box for driver subsets: covers the 12 km domain (1.8-27.5N, 60.9-91.1E)
# with a 4-5 degree margin for horizontal interpolation.
DRIVER_BOX = {"lat_min": -3.0, "lat_max": 33.0, "lon_min": 56.0, "lon_max": 96.0}

# Standardised driver file (one per event x driver), written by scripts/download/*:
#   3-D on pressure (time, plev[Pa], lat, lon):  T [K], Z [m geopotential height],
#                                                Q [kg/kg], U, V [m/s]
#   2-D (time, lat, lon): PSFC, PMSL [Pa], T2 [K], Q2 [kg/kg], U10, V10 [m/s],
#                         SKT [K], SST [K] (SKT where ocean), SEAICE [0-1], SNOW [kg/m2]
#   soil (time, soil_layer, lat, lon): ST [K], SM [m3/m3]; coordinate soil_top/soil_bot [cm]
#   static (lat, lon): LANDSEA [0/1], SOILHGT [m]
# lat strictly increasing, lon in degrees east, regular spacing.
STD_3D = ["T", "Z", "Q", "U", "V"]
STD_2D = ["PSFC", "PMSL", "T2", "Q2", "U10", "V10", "SKT", "SST", "SEAICE", "SNOW"]
STD_SOIL = ["ST", "SM"]
STD_STATIC = ["LANDSEA", "SOILHGT"]

G = 9.80665
EPS = 0.622


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config/experiment.yaml").read_text())


def times(ev: dict, step_h: int = 3) -> list[datetime]:
    t0, t1 = (datetime.fromisoformat(ev[k]) for k in ("sim_start", "sim_end"))
    out, t = [], t0
    while t <= t1:
        out.append(t)
        t += timedelta(hours=step_h)
    return out


def driver_file(event: str, driver: str) -> Path:
    return DATA / "drivers" / f"{event}_{driver}.nc"


def rh_from_q(p_pa, t_k, q):
    """Relative humidity (%) w.r.t. liquid water, exactly as WPS ungrib (rrpr.F)."""
    svp1, svp2, svp3, svpt0 = 611.2, 17.67, 29.65, 273.15
    es = svp1 * np.exp(svp2 * (t_k - svpt0) / (t_k - svp3))
    e = p_pa * q / (q * (1.0 - EPS) + EPS)
    return 100.0 * e / es


def q_from_td(p_pa, td_k):
    """Specific humidity from dew point and pressure (same Bolton/WPS svp)."""
    e = 611.2 * np.exp(17.67 * (td_k - 273.15) / (td_k - 29.65))
    return EPS * e / (p_pa - (1.0 - EPS) * e)


def check_standard(ds) -> None:
    """Raise if a standardised driver dataset is missing anything or is malformed."""
    missing = [v for v in STD_3D + STD_2D + STD_SOIL + STD_STATIC if v not in ds]
    if missing:
        raise ValueError(f"driver file missing variables: {missing}")
    lat = ds["lat"].values
    lon = ds["lon"].values
    if not (np.all(np.diff(lat) > 0) and np.allclose(np.diff(lat), np.diff(lat)[0], atol=1e-4)):
        raise ValueError("lat must be strictly increasing and regular")
    if not np.allclose(np.diff(lon), np.diff(lon)[0], atol=1e-4):
        raise ValueError("lon must be regular")
    if ds["plev"].values.max() < 90000:
        raise ValueError("plev must be in Pa")
    for v, lo, hi in [("T", 150, 340), ("Q", -1e-6, 0.05), ("PSFC", 4e4, 1.1e5),
                      ("PMSL", 8.5e4, 1.1e5), ("T2", 180, 340), ("SM", 0, 1.0)]:
        a = ds[v].values
        a = a[np.isfinite(a)]
        if a.size and (a.min() < lo or a.max() > hi):
            raise ValueError(f"{v} out of physical range [{lo},{hi}]: {a.min()}..{a.max()}")
