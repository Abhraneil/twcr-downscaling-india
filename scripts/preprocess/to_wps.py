#!/usr/bin/env python3
"""Write WPS intermediate files (format version 5) from a standardised driver file.

    python scripts/preprocess/to_wps.py E1_kerala1924 20CRv3 RUN_DIR

Writes RUN_DIR/<PREFIX>:YYYY-MM-DD_HH for every 3-hourly time, PREFIX = TWCR or ERA5,
matching fg_name in namelists/wps. ungrib is not used for either driver, so both
drivers pass through exactly the same code path.

Record layout follows WPS ungrib/src/output.F (out_format 'WPS', version 5) and is
read back by metgrid/src/read_met_module.F: big-endian Fortran sequential records
  1  int32 version (=5)
  2  char*24 hdate, f32 xfcst, char*32 map_source, char*9 field, char*25 units,
     char*46 desc, f32 xlvl, int32 nx, int32 ny, int32 iproj (0 = lat-lon)
  3  char*8 startloc, f32 startlat, f32 startlon, f32 deltalat, f32 deltalon, f32 earth_radius
  4  logical(4) is_wind_grid_rel
  5  f32 slab(nx, ny)  (Fortran order: i = lon fastest)
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import check_standard, driver_file, rh_from_q  # noqa: E402

SFC, MSL = 200100.0, 201300.0
EARTH_RADIUS_KM = 6371.229   # radius used by NCEP/ECMWF GRIB decoding in ungrib


def _rec(fh, payload: bytes) -> None:
    n = struct.pack(">i", len(payload))
    fh.write(n + payload + n)


def _s(text: str, n: int) -> bytes:
    return text.ljust(n)[:n].encode("ascii")


def write_field(fh, hdate, field, units, desc, xlvl, data2d, lat0, lon0, dlat, dlon, source):
    ny, nx = data2d.shape
    _rec(fh, struct.pack(">i", 5))
    _rec(fh, _s(hdate, 24) + struct.pack(">f", 0.0) + _s(source, 32) + _s(field, 9)
         + _s(units, 25) + _s(desc, 46) + struct.pack(">fiii", xlvl, nx, ny, 0))
    _rec(fh, _s("SWCORNER", 8) + struct.pack(">fffff", lat0, lon0, dlat, dlon, EARTH_RADIUS_KM))
    _rec(fh, struct.pack(">i", 0))                       # .false.: winds are earth-relative
    slab = np.asarray(data2d, dtype=">f4")              # (ny, nx) C order == Fortran (nx, ny)
    if not np.all(np.isfinite(slab)):
        raise ValueError(f"{field} at {xlvl} {hdate} contains non-finite values")
    _rec(fh, slab.tobytes(order="C"))


def read_intermediate(path):
    """Minimal reader mirroring metgrid's read_met_module (version 5, lat-lon only)."""
    out = []
    with open(path, "rb") as fh:
        data = fh.read()
    pos = 0

    def rec():
        nonlocal pos
        n = struct.unpack(">i", data[pos:pos + 4])[0]
        body = data[pos + 4:pos + 4 + n]
        if struct.unpack(">i", data[pos + 4 + n:pos + 8 + n])[0] != n:
            raise ValueError("record marker mismatch")
        pos += n + 8
        return body

    while pos < len(data):
        (ver,) = struct.unpack(">i", rec())
        if ver != 5:
            raise ValueError(f"version {ver}")
        h = rec()
        hdate, src = h[:24].decode(), h[28:60].decode()
        field, units, desc = h[60:69].decode(), h[69:94].decode(), h[94:140].decode()
        xfcst = struct.unpack(">f", h[24:28])[0]
        xlvl, nx, ny, iproj = struct.unpack(">fiii", h[140:156])
        if len(h) != 156 or iproj != 0:
            raise ValueError("unexpected header")
        g = rec()
        startloc = g[:8].decode()
        lat0, lon0, dlat, dlon, rad = struct.unpack(">fffff", g[8:28])
        (wind,) = struct.unpack(">i", rec())
        slab = np.frombuffer(rec(), dtype=">f4").reshape(ny, nx)
        out.append(dict(hdate=hdate, xfcst=xfcst, source=src, field=field.strip(), units=units.strip(),
                        desc=desc.strip(), xlvl=xlvl, nx=nx, ny=ny, startloc=startloc, lat0=lat0,
                        lon0=lon0, dlat=dlat, dlon=dlon, earth_radius=rad, wind_rel=bool(wind),
                        slab=slab))
    return out


def convert(ds: xr.Dataset, outdir: Path, prefix: str, source: str) -> list[Path]:
    check_standard(ds)
    lat, lon = ds["lat"].values, ds["lon"].values
    lat0, lon0 = float(lat[0]), float(lon[0])
    dlat, dlon = float(lat[1] - lat[0]), float(lon[1] - lon[0])
    outdir.mkdir(parents=True, exist_ok=True)
    files = []
    for it, t in enumerate(ds["time"].values):
        ts = np.datetime_as_string(t, unit="s").replace("T", "_")      # YYYY-MM-DD_HH:MM:SS
        hdate = ts
        f = outdir / f"{prefix}:{ts[:13]}"
        w = lambda fh, name, units, desc, lev, arr: write_field(
            fh, hdate, name, units, desc, lev, arr, lat0, lon0, dlat, dlon, source)
        x = ds.isel(time=it)
        with open(f, "wb") as fh:
            for ip, p in enumerate(x["plev"].values):
                t3 = x["T"].isel(plev=ip).values
                q3 = np.clip(x["Q"].isel(plev=ip).values, 1e-10, None)
                w(fh, "TT", "K", "Temperature", float(p), t3)
                w(fh, "RH", "%", "Relative Humidity", float(p), rh_from_q(float(p), t3, q3))
                w(fh, "SPECHUMD", "kg kg-1", "Specific Humidity", float(p), q3)
                w(fh, "UU", "m s-1", "U", float(p), x["U"].isel(plev=ip).values)
                w(fh, "VV", "m s-1", "V", float(p), x["V"].isel(plev=ip).values)
                w(fh, "GHT", "m", "Height", float(p), x["Z"].isel(plev=ip).values)
            psfc = x["PSFC"].values
            t2 = x["T2"].values
            q2 = np.clip(x["Q2"].values, 1e-10, None)
            w(fh, "PSFC", "Pa", "Surface Pressure", SFC, psfc)
            w(fh, "PMSL", "Pa", "Sea-level Pressure", MSL, x["PMSL"].values)
            w(fh, "TT", "K", "Temperature at 2 m", SFC, t2)
            w(fh, "RH", "%", "Relative Humidity at 2 m", SFC, np.clip(rh_from_q(psfc, t2, q2), 0, 100))
            w(fh, "SPECHUMD", "kg kg-1", "Specific Humidity at 2 m", SFC, q2)
            w(fh, "UU", "m s-1", "U at 10 m", SFC, x["U10"].values)
            w(fh, "VV", "m s-1", "V at 10 m", SFC, x["V10"].values)
            w(fh, "SKINTEMP", "K", "Skin temperature", SFC, x["SKT"].values)
            w(fh, "SST", "K", "Sea surface temperature", SFC, x["SST"].values)
            w(fh, "SEAICE", "proprtn", "Sea-ice fraction", SFC, x["SEAICE"].values)
            w(fh, "SNOW", "kg m-2", "Water equivalent snow depth", SFC, x["SNOW"].values)
            w(fh, "LANDSEA", "proprtn", "Land/Sea flag", SFC, x["LANDSEA"].values)
            w(fh, "SOILHGT", "m", "Terrain field of source analysis", SFC, x["SOILHGT"].values)
            for k in range(x.sizes["soil_layer"]):
                top, bot = int(x["soil_top"].values[k]), int(x["soil_bot"].values[k])
                tag = f"{top:03d}{bot:03d}"
                st = np.nan_to_num(x["ST"].isel(soil_layer=k).values, nan=float(np.nanmean(x["ST"].isel(soil_layer=k).values)))
                sm = np.nan_to_num(x["SM"].isel(soil_layer=k).values, nan=1.0)   # water points; masked by LANDSEA
                w(fh, f"ST{tag}", "K", f"T {top}-{bot} cm below ground layer", SFC, st)
                w(fh, f"SM{tag}", "fraction", f"Soil moist {top}-{bot} cm below grn layer", SFC, sm)
        files.append(f)
    return files


def main(event: str, driver: str, outdir: str) -> None:
    prefix = {"20CRv3": "TWCR", "ERA5": "ERA5"}[driver]
    ds = xr.open_dataset(driver_file(event, driver))
    files = convert(ds, Path(outdir), prefix, ds.attrs.get("source", driver))
    print(f"wrote {len(files)} intermediate files to {outdir} ({files[0].name} .. {files[-1].name})")


if __name__ == "__main__":
    main(*sys.argv[1:4])
