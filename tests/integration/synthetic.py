#!/usr/bin/env python3
"""Synthetic but physically consistent inputs for running the real model programs
(RegCM5 terrain/sst/icbc/regcm, WPS rd_intermediate/metgrid) without network access.

    python tests/integration/synthetic.py surface OUTDIR          # RegCM SURFACE/*.nc
    python tests/integration/synthetic.py driver EVENT DRIVER     # data/drivers/<EVENT>_<DRIVER>.nc

Atmosphere: a moist tropical monsoon sounding (6.5 K/km to a 100 hPa tropopause,
hydrostatic heights, RH 85% falling to 30% aloft, low-level westerlies, upper easterly
jet), a weak diurnal cycle, surface pressure consistent with an idealised Western
Ghats ridge. This tests plumbing, units and stability, not skill.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from common import DRIVER_BOX, G, check_standard, driver_file, load_config, times  # noqa: E402

RD = 287.04
PLEV_20CR = [1000, 975, 950, 925, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400,
             350, 300, 250, 200, 150, 100, 70, 50, 30, 20, 10, 5, 1]
PLEV_ERA5 = [1000, 975, 950, 925, 900, 875, 850, 825, 800, 775, 750, 700, 650, 600, 550, 500,
             450, 400, 350, 300, 250, 225, 200, 175, 150, 125, 100, 70, 50, 30, 20, 10, 7, 5, 3, 2, 1]


def coast_lon(lat):
    """Idealised Indian west coast: 77E at 8N to 72.6E at 22N, 68E north of 24N."""
    return np.where(lat < 22, 77.0 - (lat - 8.0) * (4.4 / 14.0), 72.6 - np.clip(lat - 22, 0, 4) * 1.15)


def land_and_height(lat2, lon2):
    c = coast_lon(lat2)
    land = (lon2 >= c) & (lat2 >= 7.5) & (lon2 <= 92.0) & (lat2 <= 36.0)
    ghats = 1300.0 * np.exp(-((lon2 - (c + 0.6)) / 0.35) ** 2) * (lat2 < 21.5)
    plateau = 500.0 * np.clip((lon2 - c - 0.8) / 2.0, 0, 1)
    himal = 4500.0 * np.clip((lat2 - 28.0) / 4.0, 0, 1)
    h = np.where(land, ghats + plateau + himal + 20.0, 0.0)
    return land, h.astype("float32")


def surface(outdir: Path, res_deg: float = 1.0 / 60.0) -> None:
    """RegCM SURFACE files on a regional regular grid (terrain accepts non-global files)."""
    outdir.mkdir(parents=True, exist_ok=True)
    lat = np.arange(-6.0, 42.0 + 1e-9, res_deg)
    lon = np.arange(48.0, 108.0 + 1e-9, res_deg)
    lon2, lat2 = np.meshgrid(lon, lat)
    land, h = land_and_height(lat2, lon2)
    lc = np.where(land, np.where(h > 600, 6, 1), 15).astype("float32")      # BATS: crop, forest, ocean
    tex = np.where(land, 6, 14).astype("float32")                           # loam / water
    coords = {"lat": ("lat", lat, {"units": "degrees_north"}),
              "lon": ("lon", lon, {"units": "degrees_east"})}
    for fname, var, arr in [("GMTED_DEM_30s.nc", "z", h), ("GLCC_BATS_30s.nc", "landcover", lc),
                            ("GLZB_SOIL_30s.nc", "soiltype", tex)]:
        xr.Dataset({var: (("lat", "lon"), arr)}, coords=coords).to_netcdf(outdir / fname)
        print("wrote", outdir / fname)


def sounding(p_hpa, hour):
    p = np.asarray(p_hpa, float)
    t_sfc = 300.5 + 1.5 * np.sin(2 * np.pi * (hour - 9) / 24)             # warmest ~15 LT
    t = t_sfc * (p / 1000.0) ** (RD * 0.0065 / G)
    t = np.maximum(t, 195.0)
    t = np.where(p < 100, 195.0 + 12.0 * np.log(100.0 / p) / np.log(100.0), t)
    rh = np.clip(0.85 - 0.55 * (1000.0 - p) / 700.0, 0.05, 0.85)
    rh = np.where(p < 150, 0.02, rh)
    es = 611.2 * np.exp(17.67 * (t - 273.15) / (t - 29.65))
    e = rh * es
    q = 0.622 * e / (p * 100.0 - 0.378 * e)
    u = np.interp(np.log(p), np.log([1, 100, 150, 300, 500, 700, 850, 925, 1000]),
                  [5, -10, -22, -10, 0, 8, 14, 12, 8])
    return t, q, u


def heights(p_hpa, t, q, p0=1006.0):
    """Hydrostatic geopotential height (m) of pressure levels, sea-level pressure p0."""
    order = np.argsort(-np.asarray(p_hpa))
    p, tv = np.asarray(p_hpa, float)[order], (t * (1 + 0.608 * q))[order]
    z = np.empty_like(p)
    z[0] = RD * tv[0] / G * np.log(p0 / p[0])
    for k in range(1, len(p)):
        z[k] = z[k - 1] + RD * 0.5 * (tv[k] + tv[k - 1]) / G * np.log(p[k - 1] / p[k])
    out = np.empty_like(z)
    out[order] = z
    return out


def driver(event: str, drv: str) -> Path:
    cfg = load_config()
    ev = cfg["events"][event]
    tt = times(ev, 3)
    res = 1.0 if drv == "20CRv3" else 0.25
    plev = PLEV_20CR if drv == "20CRv3" else PLEV_ERA5
    lat = np.arange(DRIVER_BOX["lat_min"], DRIVER_BOX["lat_max"] + 1e-9, res)
    lon = np.arange(DRIVER_BOX["lon_min"], DRIVER_BOX["lon_max"] + 1e-9, res)
    lon2, lat2 = np.meshgrid(lon, lat)
    land, hgt = land_and_height(lat2, lon2)
    nt, nk, ny, nx = len(tt), len(plev), len(lat), len(lon)
    T = np.empty((nt, nk, ny, nx), "f4"); Q = np.empty_like(T); U = np.empty_like(T); Z = np.empty_like(T)
    PS, T2, Q2 = (np.empty((nt, ny, nx), "f4") for _ in range(3))
    for i, t in enumerate(tt):
        tc, qc, uc = sounding(plev, t.hour + 5.5)
        zc = heights(plev, tc, qc)
        merid = 1.0 - 0.004 * (lat2 - 15.0) ** 2                       # weaker flow away from 15N
        T[i] = tc[:, None, None] - 0.03 * (lat2 - 15.0)[None]
        Q[i] = qc[:, None, None] * np.ones((1, ny, nx))
        U[i] = uc[:, None, None] * merid[None]
        Z[i] = zc[:, None, None] * np.ones((1, ny, nx))
        # surface pressure: log-interpolate pressure to the terrain height
        o = np.argsort(zc)                                             # increasing height
        ps_col = np.exp(np.interp(hgt.ravel(), zc[o], np.log(np.asarray(plev, float)[o] * 100.0)))
        PS[i] = ps_col.reshape(ny, nx)
        T2[i] = np.interp(hgt.ravel(), zc[o], tc[o]).reshape(ny, nx) - 0.5
        Q2[i] = np.interp(hgt.ravel(), zc[o], qc[o]).reshape(ny, nx)
    V = np.full_like(U, 1.0)
    pm = np.full((nt, ny, nx), 100600.0, "f4")
    sst = np.where(land, 303.0, 302.0).astype("f4")[None].repeat(nt, 0)
    ds = xr.Dataset(
        {"T": (("time", "plev", "lat", "lon"), T), "Z": (("time", "plev", "lat", "lon"), Z),
         "Q": (("time", "plev", "lat", "lon"), Q), "U": (("time", "plev", "lat", "lon"), U),
         "V": (("time", "plev", "lat", "lon"), V),
         "PSFC": (("time", "lat", "lon"), PS), "PMSL": (("time", "lat", "lon"), pm),
         "T2": (("time", "lat", "lon"), T2), "Q2": (("time", "lat", "lon"), Q2),
         "U10": (("time", "lat", "lon"), U[:, 0] * 0.6), "V10": (("time", "lat", "lon"), V[:, 0] * 0.6),
         "SKT": (("time", "lat", "lon"), sst), "SST": (("time", "lat", "lon"), sst),
         "SEAICE": (("time", "lat", "lon"), np.zeros((nt, ny, nx), "f4")),
         "SNOW": (("time", "lat", "lon"), np.zeros((nt, ny, nx), "f4")),
         "ST": (("time", "soil_layer", "lat", "lon"), np.full((nt, 4, ny, nx), 300.0, "f4")),
         "SM": (("time", "soil_layer", "lat", "lon"), np.full((nt, 4, ny, nx), 0.33, "f4")),
         "LANDSEA": (("lat", "lon"), land.astype("f4")), "SOILHGT": (("lat", "lon"), hgt)},
        coords={"time": np.array(tt, dtype="datetime64[ns]"), "plev": np.asarray(plev, float) * 100.0,
                "lat": lat, "lon": lon, "soil_layer": np.arange(4),
                "soil_top": ("soil_layer", [0, 10, 40, 100]), "soil_bot": ("soil_layer", [10, 40, 100, 200])},
        attrs={"source": f"SYNTHETIC test driver ({drv} layout)", "event": event, "driver": drv})
    ds = ds.sortby("plev", ascending=False)
    check_standard(ds)
    f = driver_file(event, drv)
    f.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(f)
    print("wrote", f)
    return f


if __name__ == "__main__":
    if sys.argv[1] == "surface":
        surface(Path(sys.argv[2]))
    else:
        driver(sys.argv[2], sys.argv[3])
