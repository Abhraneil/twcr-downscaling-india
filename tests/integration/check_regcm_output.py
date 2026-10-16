#!/usr/bin/env python3
"""Physical sanity of RegCM smoke-test output, and that the scoring reader can use it.

    python tests/integration/check_regcm_output.py RUNS_REGCM EVENT DRIVER
"""
import sys
from pathlib import Path

import numpy as np
import xarray as xr

root, ev, drv = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
ok = True
for res in ("12km", "03km"):
    out = root / f"{ev}_{drv}_{res}" / "output"
    for kind, checks in (("ATM", {"ta": (180, 320), "hus": (0, 0.03), "ua": (-80, 80), "ps": (40000, 110000)}),
                         ("SRF", {"tas": (260, 320), "pr": (0, 0.05)}),
                         ("SHF", {"pr": (0, 0.05)})):
        files = sorted(out.glob(f"*_{kind}.*.nc"))
        if not files:
            print(f"{res} {kind}: no file"); ok = False; continue
        ds = xr.open_dataset(files[0])
        nt = ds.sizes.get("time", 0)
        msg = []
        for v, (lo, hi) in checks.items():
            if v not in ds:
                msg.append(f"{v}=MISSING"); ok = False; continue
            a = ds[v].values
            bad = (~np.isfinite(a)).sum()
            if bad or np.nanmin(a) < lo or np.nanmax(a) > hi:
                ok = False
            msg.append(f"{v}[{np.nanmin(a):.4g},{np.nanmax(a):.4g}]" + (f" nan={bad}" if bad else ""))
        print(f"{res} {kind}: {files[0].name} times={nt} " + " ".join(msg))
print("REGCM SMOKE OUTPUT", "OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
