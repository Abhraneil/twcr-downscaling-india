#!/usr/bin/env python3
"""Check every key in the generated namelists against the model source code.

    python scripts/check_namelists.py --wrf /path/to/WRF --regcm /path/to/RegCM

WRF keys are checked against the `rconfig ... namelist,<group>` entries of the
Registry, plus the groups WRF declares directly in Fortran (`namelist_quilt`, read by
frame/module_io_quilt_old.F); RegCM keys against the `namelist /group/ ...` declarations
in the Fortran sources. Groups that WRF reads with a fatal error when absent must be
present. Exits non-zero if any key or group is unknown or a required group is missing.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import f90nml

ROOT = Path(__file__).resolve().parents[1]


def wrf_keys(wrf: Path) -> set[tuple[str, str]]:
    keys = set()
    for f in (wrf / "Registry").glob("*"):
        if not f.is_file():
            continue
        for line in f.read_text(errors="replace").splitlines():
            m = re.match(r"^rconfig\s+\S+\s+(\w+)\s+namelist,(\w+)", line)
            if m:
                keys.add((m.group(2).lower(), m.group(1).lower()))
    for f in (wrf / "frame").glob("*.F"):
        for m in re.finditer(r"NAMELIST\s*/\s*(\w+)\s*/([^\n]*)", f.read_text(errors="replace"), re.I):
            for n in re.findall(r"[A-Za-z_]\w*", m.group(2).split("!")[0]):
                keys.add((m.group(1).lower(), n.lower()))
    return keys


# Read by real.exe/wrf.exe with IOSTAT and wrf_error_fatal on any failure, including absence.
WRF_REQUIRED_GROUPS = {"namelist_quilt"}


def regcm_keys(regcm: Path) -> dict[str, set[str]]:
    decl: dict[str, set[str]] = {}
    for f in regcm.rglob("*.F90"):
        text = f.read_text(errors="replace")
        # join Fortran continuation lines
        text = re.sub(r"&\s*\n\s*&?", " ", text)
        for m in re.finditer(r"namelist\s*/\s*(\w+)\s*/([^\n]*)", text, re.I):
            names = re.findall(r"[A-Za-z_]\w*", m.group(2).split("!")[0])
            decl.setdefault(m.group(1).lower(), set()).update(n.lower() for n in names)
    return decl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wrf", type=Path, required=True)
    ap.add_argument("--regcm", type=Path, required=True)
    a = ap.parse_args()
    bad = []
    wk = wrf_keys(a.wrf)
    for f in sorted((ROOT / "namelists/wrf").glob("namelist.input.*")):
        nml = f90nml.read(f)
        for g in sorted(WRF_REQUIRED_GROUPS - {k.lower() for k in nml}):
            bad.append(f"{f.name}: required group &{g} missing")
        for g, items in nml.items():
            for k in items:
                if (g.lower(), k.lower()) not in wk:
                    bad.append(f"{f.name}: &{g} {k}")
    rk = regcm_keys(a.regcm)
    for f in sorted((ROOT / "namelists/regcm").glob("*.in")):
        for g, items in f90nml.read(f).items():
            if g.lower() not in rk:
                bad.append(f"{f.name}: unknown group &{g}")
                continue
            for k in items:
                if k.lower() not in rk[g.lower()]:
                    bad.append(f"{f.name}: &{g} {k}")
    print(f"WRF registry keys: {len(wk)}, RegCM namelist groups: {len(rk)}")
    if bad:
        print("UNKNOWN KEYS:\n  " + "\n  ".join(bad))
        return 1
    print("All namelist keys exist in the model sources.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
