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


SM_MIN = 0.01   # m3/m3: below the lowest soil water ERA5 (HTESSEL) holds on real land


def fill_dry_land(sm: xr.DataArray, land: xr.DataArray) -> xr.DataArray:
    """Replace land soil water below SM_MIN by the nearest valid land value (per layer and time)."""
    from scipy.ndimage import distance_transform_edt
    a = sm.transpose("time", "soil_layer", "lat", "lon").values.copy()
    lm = land.transpose("lat", "lon").values
    n = 0
    for t in range(a.shape[0]):
        for k in range(a.shape[1]):
            f = a[t, k]
            bad = lm & ~(f >= SM_MIN)
            if not bad.any():
                continue
            good = lm & (f >= SM_MIN)
            if not good.any():
                raise ValueError("no valid ERA5 soil water on land")
            _, (ii, jj) = distance_transform_edt(~good, return_indices=True)
            f[bad] = f[ii[bad], jj[bad]]
            n += int(bad.sum())
    if n:
        print(f"SM: {n} land values below {SM_MIN} m3/m3 filled from the nearest valid land point", flush=True)
    return sm.transpose("time", "soil_layer", "lat", "lon").copy(data=a)


def write_atomic(ds: xr.Dataset, path: Path) -> None:
    tmp = path.with_name(path.name + ".part")
    ds.to_netcdf(tmp)
    tmp.replace(path)


def have(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def too_large(err: Exception) -> bool:
    m = str(err).lower()
    return "cost limits" in m or "too large" in m


class Fetcher:
    """cdsapi retrieval that never leaves a partial file and splits requests CDS rejects as
    too large (CDS 'cost limits exceeded'): first one request per variable, then halves of
    the day list. Pieces are normalised (norm) and merged; norm is idempotent, so a merged
    file reads exactly like a single CDS download."""

    def __init__(self):
        self._client = None

    def retrieve(self, dataset: str, req: dict, target: Path) -> None:
        if have(target):
            return
        if self._client is None:                 # created only if something must be fetched
            import cdsapi
            self._client = cdsapi.Client()
        tmp = target.with_name(target.name + ".part")
        self._client.retrieve(dataset, req, str(tmp))
        tmp.replace(target)

    def get(self, dataset: str, req: dict, target: Path) -> None:
        if have(target):
            return
        try:
            self.retrieve(dataset, req, target)
            return
        except Exception as err:                 # noqa: BLE001 - re-raised unless 'too large'
            if not too_large(err):
                raise
            print(f"  CDS: request for {target.name} too large; splitting", flush=True)
        if len(req["variable"]) > 1:
            parts = []
            for v in req["variable"]:
                fv = target.with_name(f"{target.stem}_{v}.nc")
                self.get(dataset, req | {"variable": [v]}, fv)
                parts.append(norm(open_cds(fv)))
            write_atomic(xr.merge(parts, compat="override", join="exact"), target)
        elif len(req["day"]) > 1:
            h = len(req["day"]) // 2
            parts = []
            for k, days in enumerate((req["day"][:h], req["day"][h:])):
                fd = target.with_name(f"{target.stem}_d{k}.nc")
                self.get(dataset, req | {"day": days}, fd)
                parts.append(norm(open_cds(fd)))
            write_atomic(xr.concat(parts, dim="time").sortby("time"), target)
        else:
            raise RuntimeError(f"CDS rejects even a single-variable, single-day request for {target.name}")


def main(event: str) -> None:
    cfg = load_config()
    ev = cfg["events"][event]
    tt = times(ev, 3)
    if len({(t.year, t.month) for t in tt}) != 1:
        raise RuntimeError("event spans two months; split the request")
    raw = DATA / "raw" / "era5"
    raw.mkdir(parents=True, exist_ok=True)
    fpl, fsl = raw / f"{event}_pl.nc", raw / f"{event}_sl.nc"
    cds = Fetcher()
    # 5 variables x 37 levels x 7 days x 8 times exceeds the CDS cost limit in one request,
    # so pressure levels go one variable per request from the start.
    if not have(fpl):
        parts = []
        for v in PL_VARS:
            fv = raw / f"{event}_pl_{v}.nc"
            cds.get("reanalysis-era5-pressure-levels",
                    request(tt) | {"variable": [v], "pressure_level": [str(p) for p in PLEVS]}, fv)
            parts.append(norm(open_cds(fv)))
        write_atomic(xr.merge(parts, compat="override", join="exact"), fpl)
    cds.get("reanalysis-era5-single-levels", request(tt) | {"variable": SL_VARS}, fsl)
    ftp = raw / f"{event}_tp.nc"
    r = request(tt) | {"variable": ["total_precipitation"], "time": [f"{h:02d}:00" for h in range(24)]}
    r["day"] = sorted({t.strftime("%d") for t in tt} | {(tt[-1] + timedelta(days=1)).strftime("%d")})
    cds.get("reanalysis-era5-single-levels", r, ftp)
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
    # ERA5 specific humidity has small negative values (a numerical artefact of the
    # analysis, ~1e-6 kg/kg); set them to zero. Anything far below zero is a real problem.
    qmin = float(std["Q"].min())
    if qmin < 0:
        if qmin < -1e-4:
            raise ValueError(f"ERA5 Q minimum {qmin:.3e} kg/kg: not a rounding artefact")
        print(f"Q: {int((std['Q'] < 0).sum())} negative values (min {qmin:.2e} kg/kg) set to 0", flush=True)
        std["Q"] = std["Q"].clip(min=0.0)
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
    # ERA5 soil water and snow depth have small negative values from interpolation to the
    # 0.25 degree grid (mostly at coasts); set them to zero, stop if they are not small.
    for v, tol in [("SM", -0.05), ("SNOW", -1.0)]:
        vmin = float(std[v].min())
        if vmin < 0:
            if vmin < tol:
                raise ValueError(f"ERA5 {v} minimum {vmin:.3g}: not an interpolation artefact")
            neg = std[v] < 0
            print(f"{v}: {int(neg.sum())} negative values (min {vmin:.2g}; "
                  f"{int((neg & (std['LANDSEA'] > 0.5)).sum())} on land) set to 0", flush=True)
            std[v] = std[v].clip(min=0.0)
    # Zeroing those values leaves a few land points (mostly at coasts) with no soil water at all,
    # which is unphysical in the monsoon and made WRF's first ERA5 run crash after 8 h. Give every
    # land value below SM_MIN the value of the nearest land point that has valid soil water, in the
    # same layer and time. Sea points are not used by the land models and are left as they are.
    std["SM"] = fill_dry_land(std["SM"], std["LANDSEA"] > 0.5)
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
