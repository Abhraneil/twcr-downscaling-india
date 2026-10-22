#!/usr/bin/env python3
"""Keep the part of the model output that the results need, so the raw runs can be deleted.

    python scripts/postprocess/slim_archive.py --runs-root RUNS --out DEST

Writes DEST with the same layout as RUNS, so every script that reads model output
(extract_precip.py, story_figures.py) runs on DEST unchanged:

  wrf/<event>_<driver>/wrfout_d0[12]_*   Times, XLAT, XLONG, HGT, LANDMASK, RAINC, RAINNC,
                                         RAINSH (hourly, as written), global attributes
  regcm/<run>/output/*SHF*.nc            pr and its coordinates (hourly)
  wps/<event>_<driver>/geo_em.d0[12].nc  XLAT_M, XLONG_M, HGT_M, LANDMASK
  every run directory: namelist.input / namelist.wps / regcm.in*, timing.txt,
                       resumes.log, rsl.error.0000, regcm.log (whichever exist)

Values are copied bit for bit (netCDF-4, lossless deflate) and every copied variable is read
back and compared with the original; MANIFEST.txt lists each file with its size and sha256.
The script exits non-zero if anything differs or is missing, and deletes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import load_config  # noqa: E402

WRF_VARS = ["Times", "XTIME", "XLAT", "XLONG", "HGT", "LANDMASK", "RAINC", "RAINNC", "RAINSH"]
GEO_VARS = ["Times", "XLAT_M", "XLONG_M", "HGT_M", "LANDMASK"]
REGCM_VARS = ["pr", "time", "time_bnds", "xlat", "xlon", "jx", "iy", "x", "y", "crs", "rcm_map",
              "topo", "mask"]
SMALL_FILES = ["namelist.input", "namelist.wps", "timing.txt", "resumes.log", "rsl.error.0000",
               "regcm.log", "restarts_ok.txt"]


def copy_subset(src: Path, dst: Path, keep: list[str], required: list[str]) -> list[str]:
    """Copy the variables in `keep` that exist (raw values, attributes, dimensions)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(src) as s:
        names = [v for v in keep if v in s.variables]
        if "pr" in names and "coordinates" in s.variables["pr"].ncattrs():
            names += [c for c in s.variables["pr"].coordinates.split() if c in s.variables and c not in names]
        missing = [v for v in required if v not in names]
        if missing:
            raise KeyError(f"{src}: lacks {missing}")
        with Dataset(dst, "w", format="NETCDF4") as d:
            d.setncatts({k: s.getncattr(k) for k in s.ncattrs()})
            for dim in sorted({x for v in names for x in s.variables[v].dimensions}):
                sd = s.dimensions[dim]
                d.createDimension(dim, None if sd.isunlimited() else len(sd))
            for v in names:
                sv = s.variables[v]
                sv.set_auto_maskandscale(False)
                fill = sv.getncattr("_FillValue") if "_FillValue" in sv.ncattrs() else None
                dv = d.createVariable(v, sv.datatype, sv.dimensions, zlib=True, complevel=4,
                                      fill_value=fill)
                dv.setncatts({k: sv.getncattr(k) for k in sv.ncattrs() if k != "_FillValue"})
                dv.set_auto_maskandscale(False)
                dv[:] = sv[:]
    return names


def same(src: Path, dst: Path, names: list[str]) -> list[str]:
    bad = []
    with Dataset(src) as s, Dataset(dst) as d:
        for v in names:
            s.variables[v].set_auto_maskandscale(False)
            d.variables[v].set_auto_maskandscale(False)
            a, b = np.asarray(s.variables[v][:]), np.asarray(d.variables[v][:])
            if a.shape != b.shape or not np.array_equal(a, b, equal_nan=a.dtype.kind == "f"):
                bad.append(v)
    return bad


def sha256(f: Path) -> str:
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    runs, out = a.runs_root.resolve(), a.out.resolve()
    if out == runs or runs in out.parents:
        sys.exit("--out must be outside --runs-root")
    cfg = load_config()
    jobs = []   # (src, dst, keep, required)
    smalls = []
    problems = []
    for ev_name, ev in cfg["events"].items():
        for drv in ev["drivers"]:
            w = runs / "wrf" / f"{ev_name}_{drv}"
            files = sorted(w.glob("wrfout_d0*"))
            if not any(f.name.startswith("wrfout_d02") for f in files):
                problems.append(f"{w}: no wrfout_d02 files")
            jobs += [(f, out / "wrf" / w.name / f.name, WRF_VARS, ["Times", "XLAT", "XLONG", "RAINC", "RAINNC"])
                     for f in files]
            smalls += [w / n for n in SMALL_FILES]
            g = runs / "wps" / f"{ev_name}_{drv}"
            for dom in ("d01", "d02"):
                f = g / f"geo_em.{dom}.nc"
                if f.exists():
                    jobs.append((f, out / "wps" / g.name / f.name, GEO_VARS, ["XLAT_M", "XLONG_M", "HGT_M", "LANDMASK"]))
                else:
                    problems.append(f"{f}: missing")
            smalls.append(g / "namelist.wps")
            for res in ("12km", "03km"):
                r = runs / "regcm" / f"{ev_name}_{drv}_{res}"
                files = sorted((r / "output").glob("*SHF*.nc"))
                if not files:
                    problems.append(f"{r}/output: no SHF files")
                jobs += [(f, out / "regcm" / r.name / "output" / f.name, REGCM_VARS, ["pr", "time", "xlat", "xlon"])
                         for f in files]
                smalls += [r / n for n in SMALL_FILES] + sorted(r.glob("regcm.in*"))
    if problems:
        print("\n".join(problems))
        sys.exit("not all runs are complete in --runs-root; nothing written")

    src_bytes = 0
    for i, (src, dst, keep, req) in enumerate(jobs, 1):
        names = copy_subset(src, dst, keep, req)
        bad = same(src, dst, names)
        if bad:
            sys.exit(f"{dst}: read-back differs for {bad}")
        src_bytes += src.stat().st_size
        print(f"[{i}/{len(jobs)}] {dst.relative_to(out)}  ({', '.join(names)})", flush=True)
    for f in smalls:
        if f.is_file():
            dst = out / f.relative_to(runs)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)

    lines, total = [], 0
    for f in sorted(p for p in out.rglob("*") if p.is_file() and p.name != "MANIFEST.txt"):
        size = f.stat().st_size
        total += size
        lines.append(f"{sha256(f)}  {size:>12d}  {f.relative_to(out)}")
    (out / "MANIFEST.txt").write_text("\n".join(lines) + "\n")
    print(f"\n{len(jobs)} netCDF files copied and verified ({src_bytes / 1e9:.1f} GB of originals "
          f"read), {len(lines)} files, {total / 1e9:.2f} GB in {out}")
    print("MANIFEST.txt written; the original runs were not touched")


if __name__ == "__main__":
    main()
