#!/usr/bin/env python3
"""Download the 20CRv3 ensemble mean for one event and write the standardised driver file.

    python scripts/download/get_20crv3.py E1_kerala1924
    python scripts/download/get_20crv3.py E2_mumbai2005

Source: NOAA PSL THREDDS, Datasets/20thC_ReanV3 (3-hourly, 1 degree regular grid).
Directory suffix is SI for years up to 1980 and MO from 1981 (PSL convention).
Only the regional box and the event window are transferred (OPeNDAP subsetting).
File names are resolved from the THREDDS catalog at run time, so a renamed file
fails loudly instead of silently picking the wrong variable.

Output: data/drivers/<event>_20CRv3.nc in the format defined in scripts/common.py.
"""
from __future__ import annotations

import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DRIVER_BOX, check_standard, driver_file, load_config, times  # noqa: E402

BASE = "https://psl.noaa.gov/thredds"
DS = "Datasets/20thC_ReanV3"

# (standard name, PSL directory stem, PSL variable prefix, preferred level tag or None)
FIELDS = [
    ("T", "prs", "air", None), ("Z", "prs", "hgt", None), ("Q", "prs", "shum", None),
    ("U", "prs", "uwnd", None), ("V", "prs", "vwnd", None),
    ("T2", "2m", "air", "2m"), ("Q2", "2m", "shum", "2m"),
    ("U10", "10m", "uwnd", "10m"), ("V10", "10m", "vwnd", "10m"),
    ("PSFC", "sfc", "pres", "sfc"), ("SKT", "sfc", "skt", None), ("SEAICE", "sfc", "icec", None),
    ("PMSL", "misc", "prmsl", None),
    ("ST", "subsfc", "tsoil", None), ("SM", "subsfc", "soilw", None),
    ("SNOW", "accums", "weasd", None),
    ("PRATE", "sfc", "prate", None),
]
NOAH_LAYERS_CM = [(0, 10), (10, 40), (40, 100), (100, 200)]


def stream(year: int) -> str:
    return "SI" if year <= 1980 else "MO"


def catalog(dirname: str) -> list[str]:
    url = f"{BASE}/catalog/{DS}/{dirname}/catalog.xml"
    with urllib.request.urlopen(url, timeout=120) as r:
        root = ET.fromstring(r.read())
    return [e.get("name") for e in root.iter() if e.get("name", "").endswith(".nc")]


def resolve(files: list[str], prefix: str, year: int | None, level: str | None) -> str:
    yr = rf"\.{year}" if year is not None else ""
    pat = re.compile(rf"^{re.escape(prefix)}(\.[A-Za-z0-9_]+)?{yr}\.nc$")
    cands = [f for f in files if pat.match(f)]
    if level:
        pref = [f for f in cands if f.startswith(f"{prefix}.{level}.")]
        cands = pref or cands
    else:
        plain = f"{prefix}.{year}.nc" if year is not None else f"{prefix}.nc"
        cands = [f for f in cands if f == plain] or cands
    if len(cands) != 1:
        raise RuntimeError(f"cannot resolve {prefix} {year} {level}: candidates {cands}")
    return cands[0]


def open_remote(dirname: str, fname: str, retries: int = 4) -> xr.Dataset:
    url = f"{BASE}/dodsC/{DS}/{dirname}/{fname}"
    for k in range(retries):
        try:
            return xr.open_dataset(url, engine="netcdf4", decode_times=True)
        except OSError as err:  # transient THREDDS errors
            if k == retries - 1:
                raise RuntimeError(f"OPeNDAP open failed for {url}: {err}") from err
            time.sleep(10 * (k + 1))


def subset(da: xr.DataArray, t0=None, t1=None) -> xr.DataArray:
    da = da.sortby("lat")
    da = da.sel(lat=slice(DRIVER_BOX["lat_min"], DRIVER_BOX["lat_max"]),
                lon=slice(DRIVER_BOX["lon_min"], DRIVER_BOX["lon_max"]))
    if t0 is not None:
        da = da.sel(time=slice(t0, t1))
    return da.load()


def main(event: str) -> None:
    cfg = load_config()
    ev = cfg["events"][event]
    tt = times(ev, 3)
    t0, t1 = np.datetime64(tt[0]), np.datetime64(tt[-1])
    year = tt[0].year
    s = stream(year)
    out = {}
    cache: dict[str, list[str]] = {}
    for std, stem, prefix, level in FIELDS:
        d = stem + s
        cache.setdefault(d, catalog(d))
        fname = resolve(cache[d], prefix, year, level)
        print(f"{std:7s} <- {d}/{fname}", flush=True)
        ds = open_remote(d, fname)
        var = [v for v in ds.data_vars if ds[v].ndim >= 3]
        if len(var) != 1:
            raise RuntimeError(f"{fname}: expected one data variable, found {var}")
        da = subset(ds[var[0]], t0, t1)
        out[std] = (da, ds)
    # static fields
    d = "timeInvariant" + s
    cache.setdefault(d, catalog(d))
    land = subset(open_remote(d, "land.nc")["land"])
    hgt = subset(open_remote(d, "hgt.sfc.nc")["hgt"])
    land = land.isel(time=0, drop=True) if "time" in land.dims else land
    hgt = hgt.isel(time=0, drop=True) if "time" in hgt.dims else hgt

    target = out["T"][0]
    lat, lon = target["lat"], target["lon"]
    ntime = len(tt)
    std = xr.Dataset(coords={"time": ("time", np.array(tt, dtype="datetime64[ns]")),
                             "lat": lat.values, "lon": lon.values})

    def on_target(da, mask_land=False):
        if "time" in da.dims:
            da = da.sel(time=std["time"].values)   # exact 3-hourly times; KeyError if any is missing
        if da.sizes["lat"] == lat.size and np.allclose(da["lat"], lat) and np.allclose(da["lon"], lon):
            return da
        # different native grid (e.g. Gaussian surface-flux grid): fill water with nearest
        # land value before interpolating so coastlines do not mix land and sea values
        if mask_land:
            da = da.ffill("lon").bfill("lon").ffill("lat").bfill("lat")
        return da.interp(lat=lat, lon=lon, method="linear")

    for name in ["T", "Z", "Q", "U", "V"]:
        da = out[name][0]
        levname = [c for c in da.dims if c not in ("time", "lat", "lon")][0]
        da = da.rename({levname: "plev"})
        da = da.assign_coords(plev=(da["plev"].values * 100.0).astype("float64"))  # hPa -> Pa
        da = da.sortby("plev", ascending=False)
        std[name] = on_target(da).astype("float32")
    for name in ["T2", "Q2", "U10", "V10", "PSFC", "SKT", "SEAICE", "PMSL", "SNOW"]:  # PRATE handled below
        da = out[name][0]
        extra = [c for c in da.dims if c not in ("time", "lat", "lon")]
        if extra:
            da = da.isel({c: 0 for c in extra}, drop=True)
        std[name] = on_target(da).astype("float32")
    for name in ["ST", "SM"]:
        da = out[name][0]
        levname = [c for c in da.dims if c not in ("time", "lat", "lon")][0]
        if da.sizes[levname] != 4:
            raise RuntimeError(f"{name}: expected 4 Noah soil layers, got {da.sizes[levname]}")
        print(f"{name} native soil level values: {da[levname].values} (mapped to Noah 0-10/10-40/40-100/100-200 cm)")
        da = da.rename({levname: "soil_layer"}).assign_coords(soil_layer=np.arange(4))
        std[name] = on_target(da, mask_land=True).astype("float32")
    std = std.assign_coords(soil_top=("soil_layer", [a for a, _ in NOAH_LAYERS_CM]),
                            soil_bot=("soil_layer", [b for _, b in NOAH_LAYERS_CM]))
    std["LANDSEA"] = (on_target(land) > 0.5).astype("float32")
    std["SOILHGT"] = on_target(hgt).astype("float32")
    std["SEAICE"] = std["SEAICE"].fillna(0.0)
    std["SNOW"] = std["SNOW"].fillna(0.0)
    std["SST"] = std["SKT"]                      # SKT equals the prescribed SST over open ocean

    # Driver precipitation (baseline for added value), kept out of the standard file.
    pr = out["PRATE"][0]
    pr = pr.sel(time=std["time"].values)
    prf = driver_file(event, "20CRv3").with_name(f"{event}_20CRv3_precip.nc")
    prf.parent.mkdir(parents=True, exist_ok=True)
    xr.Dataset({"pr": pr.astype("float32")}).assign_attrs(
        units="kg m-2 s-1", interval_hours=3,
        convention="value at time t = mean rate over the 3 h ending at t (see docs/metrics.md)").to_netcdf(prf)

    if std.sizes["time"] != ntime:
        raise RuntimeError(f"expected {ntime} 3-hourly times, got {std.sizes['time']}")
    std.attrs.update(source="NOAA-CIRES-DOE 20CRv3 ensemble mean via PSL THREDDS",
                     event=event, driver="20CRv3", grid="1 degree regular lat-lon")
    check_standard(std)
    f = driver_file(event, "20CRv3")
    f.parent.mkdir(parents=True, exist_ok=True)
    std.to_netcdf(f)
    print(f"wrote {f}  ({f.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main(sys.argv[1])
