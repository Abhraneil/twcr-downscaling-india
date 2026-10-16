#!/usr/bin/env python3
"""Download ERA5 for an event (control driver) and write the standardised driver file.

    python scripts/download/get_era5.py E2_mumbai2005

Needs a Copernicus CDS account and ~/.cdsapirc (https://cds.climate.copernicus.eu/how-to-api).
ERA5 is subsampled to 3-hourly so that it reaches the regional models at the same
boundary update interval as 20CRv3; the only difference between the two runs is the driver.

Output: data/drivers/<event>_ERA5.nc in the format defined in scripts/common.py.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA, DRIVER_BOX, G, check_standard, driver_file, load_config, q_from_td, times  # noqa: E402

PLEVS = [1, 2, 3, 5, 7, 10, 20, 30, 50, 70, 100, 125, 150, 175, 200, 225, 250, 300, 350, 400,
         450, 500, 550, 600, 650, 700, 750, 775, 800, 825, 850, 875, 900, 925, 950, 975, 1000]
PL_VARS = ["temperature", "geopotential", "specific_humidity",
           "u_component_of_wind", "v_component_of_wind"]
SL_VARS = ["surface_pressure", "mean_sea_level_pressure", "2m_temperature", "2m_dewpoint_temperature",
           "10m_u_component_of_wind", "10m_v_component_of_wind", "skin_temperature",
           "sea_surface_temperature", "sea_ice_cover", "snow_depth",
           "soil_temperature_level_1", "soil_temperature_level_2", "soil_temperature_level_3",
           "soil_temperature_level_4", "volumetric_soil_water_layer_1", "volumetric_soil_water_layer_2",
           "volumetric_soil_water_layer_3", "volumetric_soil_water_layer_4",
           "land_sea_mask", "geopotential"]
ERA5_SOIL_CM = [(0, 7), (7, 28), (28, 100), (100, 289)]


def request(tt):
    days = sorted({t.strftime("%d") for t in tt})
    return {
        "product_type": ["reanalysis"],
        "year": [tt[0].strftime("%Y")], "month": [tt[0].strftime("%m")], "day": days,
        "time": [f"{h:02d}:00" for h in range(0, 24, 3)],
        "area": [DRIVER_BOX["lat_max"], DRIVER_BOX["lon_min"], DRIVER_BOX["lat_min"], DRIVER_BOX["lon_max"]],
        "data_format": "netcdf", "download_format": "unarchived",
    }


def open_cds(path: Path) -> xr.Dataset:
    """Open a CDS download; new CDS may deliver a zip of several netCDF files."""
    with open(path, "rb") as fh:
        magic = fh.read(2)
    if magic != b"PK":
        return xr.open_dataset(path)
    import zipfile
    dest = path.with_suffix(".unzipped")
    with zipfile.ZipFile(path) as z:
        z.extractall(dest)
    parts = [xr.open_dataset(f) for f in sorted(dest.glob("*.nc"))]
    if not parts:
        raise RuntimeError(f"{path} is a zip without netCDF members")
    return xr.merge(parts, compat="override", join="exact")


def norm(ds):
    ren = {}
    for a, b in [("valid_time", "time"), ("latitude", "lat"), ("longitude", "lon"),
                 ("pressure_level", "plev"), ("level", "plev")]:
        if a in ds.dims or a in ds.coords:
            ren[a] = b
    ds = ds.rename(ren)
    drop = [c for c in ("number", "expver") if c in ds.coords or c in ds.dims]
    if "expver" in ds.dims:
        ds = ds.reduce(np.nanmax, dim="expver")
    return ds.drop_vars([c for c in drop if c in ds.variables], errors="ignore").sortby("lat")


def main(event: str) -> None:
    import cdsapi  # imported here so the rest of the repo does not need it

    cfg = load_config()
    ev = cfg["events"][event]
    tt = times(ev, 3)
    if len({(t.year, t.month) for t in tt}) != 1:
        raise RuntimeError("event spans two months; split the request")
    raw = DATA / "raw" / "era5"
    raw.mkdir(parents=True, exist_ok=True)
    fpl, fsl = raw / f"{event}_pl.nc", raw / f"{event}_sl.nc"
    _c = []
    def c_retrieve(*args):                      # client created only if something must be fetched
        if not _c:
            _c.append(cdsapi.Client())
        _c[0].retrieve(*args)
    if not fpl.exists():
        r = request(tt) | {"variable": PL_VARS, "pressure_level": [str(p) for p in PLEVS]}
        c_retrieve("reanalysis-era5-pressure-levels", r, str(fpl))
    if not fsl.exists():
        c_retrieve("reanalysis-era5-single-levels", request(tt) | {"variable": SL_VARS}, str(fsl))
    ftp = raw / f"{event}_tp.nc"
    if not ftp.exists():
        r = request(tt) | {"variable": ["total_precipitation"], "time": [f"{h:02d}:00" for h in range(24)]}
        days = sorted({t.strftime("%d") for t in tt} | {(tt[-1] + timedelta(days=1)).strftime("%d")})
        r["day"] = days
        c_retrieve("reanalysis-era5-single-levels", r, str(ftp))
    tp = norm(open_cds(ftp))["tp"]
    # ERA5 tp at time t is the accumulation over the hour ending at t (m) -> rate
    prf = driver_file(event, "ERA5").with_name(f"{event}_ERA5_precip.nc")
    prf.parent.mkdir(parents=True, exist_ok=True)
    xr.Dataset({"pr": (tp * 1000.0 / 3600.0).astype("float32")}).assign_attrs(
        units="kg m-2 s-1", interval_hours=1,
        convention="value at time t = mean rate over the hour ending at t").to_netcdf(prf)
    pl, sl = norm(open_cds(fpl)), norm(open_cds(fsl))
    tsel = np.array(tt, dtype="datetime64[ns]")
    pl, sl = pl.sel(time=tsel), sl.sel(time=tsel)

    std = xr.Dataset(coords={"time": tsel, "lat": pl["lat"].values, "lon": pl["lon"].values})
    pl = pl.assign_coords(plev=pl["plev"].values * 100.0).sortby("plev", ascending=False)
    for a, b in [("T", "t"), ("Q", "q"), ("U", "u"), ("V", "v")]:
        std[a] = pl[b].astype("float32")
    std["Z"] = (pl["z"] / G).astype("float32")
    std["PSFC"], std["PMSL"] = sl["sp"], sl["msl"]
    std["T2"], std["U10"], std["V10"] = sl["t2m"], sl["u10"], sl["v10"]
    std["Q2"] = q_from_td(sl["sp"], sl["d2m"])
    std["SKT"] = sl["skt"]
    std["SST"] = sl["sst"].fillna(sl["skt"])          # land points carry skin temperature
    std["SEAICE"] = sl["siconc"].fillna(0.0)
    std["SNOW"] = sl["sd"] * 1000.0                  # m water equivalent -> kg m-2
    std["ST"] = xr.concat([sl[f"stl{k}"] for k in range(1, 5)], dim="soil_layer")
    std["SM"] = xr.concat([sl[f"swvl{k}"] for k in range(1, 5)], dim="soil_layer")
    std = std.assign_coords(soil_layer=np.arange(4),
                            soil_top=("soil_layer", [a for a, _ in ERA5_SOIL_CM]),
                            soil_bot=("soil_layer", [b for _, b in ERA5_SOIL_CM]))
    std["ST"] = std["ST"].transpose("time", "soil_layer", "lat", "lon")
    std["SM"] = std["SM"].transpose("time", "soil_layer", "lat", "lon")
    std["LANDSEA"] = (sl["lsm"].isel(time=0, drop=True) > 0.5).astype("float32")
    std["SOILHGT"] = (sl["z"].isel(time=0, drop=True) / G).astype("float32")
    for v in std.data_vars:
        std[v] = std[v].astype("float32")
    std.attrs.update(source="ERA5 via Copernicus CDS", event=event, driver="ERA5",
                     grid="0.25 degree regular lat-lon")
    check_standard(std)
    f = driver_file(event, "ERA5")
    f.parent.mkdir(parents=True, exist_ok=True)
    std.to_netcdf(f)
    print(f"wrote {f}  ({f.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main(sys.argv[1])
