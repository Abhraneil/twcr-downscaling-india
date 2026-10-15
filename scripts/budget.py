#!/usr/bin/env python3
"""Compute and storage budget for the full run matrix, from config/experiment.yaml.

    python scripts/budget.py            # prints markdown tables
    python scripts/budget.py --md docs/budget.md

Cost model (stated, not measured): core-seconds per grid column-level per
time step. The bracket 4-8 microseconds covers WRF-ARW and RegCM5-MOLOCH with
full physics on current x86 cores. Replace COST_LO/COST_HI with the value
measured in the 1-day benchmark (docs/runbook.md, step 5) and re-run.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COST_LO, COST_HI = 4e-6, 8e-6          # core-s per point-level-step
NODE_CORES = 64
PAR_EFF = 0.8                           # parallel efficiency assumed on one node
B = 4                                   # bytes per float32

# Storage prices, USD per GiB-month (Google Cloud Storage, us-central1 list price,
# hourly rates on cloud.google.com/storage/pricing x 730 h). Mumbai is slightly higher.
PRICES = {"GCS Standard": 0.000027397 * 730, "GCS Coldline": 0.000005479 * 730,
          "GCS Archive": 0.000001644 * 730}


def hours(ev):
    s, e = (datetime.fromisoformat(ev[k]) for k in ("sim_start", "sim_end"))
    return (e - s).total_seconds() / 3600


def point_steps(nx, ny, nz, dt, h):
    return nx * ny * nz * h * 3600 / dt


def wrf_out_gb(nx, ny, nz, frames):
    # per column: ~10 kept 3-D fields on nz(+1) levels + ~150 2-D/soil fields (hydrometeors dropped)
    per_col = 10 * (nz + 1) + 150
    return nx * ny * per_col * B * frames / 1e9


def regcm_out_gb(nx, ny, nz, h):
    atm = nx * ny * (8 * nz + 10) * B * (h / 3 + 1)     # ATM 3-hourly
    srf = nx * ny * 45 * B * (h + 1)                    # SRF hourly
    shf = nx * ny * 2 * B * (h + 1)                     # SHF hourly precipitation
    sts = nx * ny * 20 * B * (h / 24 + 1)
    return (atm + srf + shf + sts) / 1e9


def build_runs(cfg):
    o, n = cfg["outer_domain"], cfg["inner_domain"]
    runs = []
    for ev_name, ev in cfg["events"].items():
        h = hours(ev)
        for drv in ev["drivers"]:
            # WRF: d01 12 km (dt 60 s) + d02 3 km (dt 15 s) in one one-way nested run
            ps = (point_steps(o["nx"], o["ny"], o["vertical_levels_wrf"], 5 * o["dx_km"], h)
                  + point_steps(n["nx"], n["ny"], o["vertical_levels_wrf"], 5 * o["dx_km"] / n["ratio"], h))
            out = (wrf_out_gb(o["nx"], o["ny"], o["vertical_levels_wrf"], h + 1)
                   + wrf_out_gb(n["nx"], n["ny"], o["vertical_levels_wrf"], h + 1))
            runs.append(dict(model="WRF 12+3 km", event=ev_name, driver=drv, hours=h, ps=ps, out=out))
            ps12 = point_steps(o["nx"] + 1, o["ny"] + 1, o["vertical_levels_regcm"], 90, h)
            runs.append(dict(model="RegCM5 12 km", event=ev_name, driver=drv, hours=h, ps=ps12,
                             out=regcm_out_gb(o["nx"], o["ny"], o["vertical_levels_regcm"], h)))
            ps3 = point_steps(n["nx"] + 1, n["ny"] + 1, n["vertical_levels_regcm"], 30, h)
            runs.append(dict(model="RegCM5 3 km", event=ev_name, driver=drv, hours=h, ps=ps3,
                             out=regcm_out_gb(n["nx"], n["ny"], n["vertical_levels_regcm"], h)))
    return runs


def inputs_gb(cfg):
    """Driver and observation volumes for the regional subsets used here."""
    nt = {k: hours(ev) / 3 + 1 for k, ev in cfg["events"].items()}
    box_1deg = 41 * 37            # 56-96E x -3-33N at 1 deg (20CRv3 PSL grid)
    box_q = 161 * 145             # same box at 0.25 deg (ERA5)
    twcr = sum((5 * 28 + 15) * box_1deg * B * n for n in nt.values()) / 1e9
    era5 = (5 * 37 + 12) * box_q * B * nt["E2_mumbai2005"] / 1e9
    return {
        "20CRv3 regional subsets (OPeNDAP, both events)": twcr,
        "20CRv3 whole annual global files, if subsetting fails (1924 + 2005)": 2 * 36.0,
        "ERA5 regional subset (2005, 37 levels, 3-hourly)": era5,
        "IMD 0.25 deg rainfall (1924, 2005)": 2 * 0.026,
        "WPS static geography (already on the HPC)": 29.0,
        "RegCM5 static surface data (GMTED, land use, texture)": 15.0,
    }


def table(rows, headers):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", type=Path)
    a = ap.parse_args()
    cfg = yaml.safe_load((ROOT / "config/experiment.yaml").read_text())
    runs = build_runs(cfg)
    rows, tlo, thi, tout = [], 0.0, 0.0, 0.0
    for r in runs:
        lo, hi = r["ps"] * COST_LO / 3600, r["ps"] * COST_HI / 3600
        wlo, whi = lo / NODE_CORES / PAR_EFF, hi / NODE_CORES / PAR_EFF
        tlo, thi, tout = tlo + lo, thi + hi, tout + r["out"]
        rows.append([r["model"], r["event"], r["driver"], f"{r['hours']:.0f}",
                     f"{lo:,.0f}-{hi:,.0f}", f"{wlo:.1f}-{whi:.1f}", f"{r['out']:.1f}"])
    rows.append(["**Total**", f"{len(runs)} runs", "", "", f"**{tlo:,.0f}-{thi:,.0f}**",
                 f"**{tlo/NODE_CORES/PAR_EFF:.0f}-{thi/NODE_CORES/PAR_EFF:.0f}**", f"**{tout:.0f}**"])
    md = ["## Compute and model output", "",
          table(rows, ["Model", "Event", "Driver", "Sim h", "Core-hours", "Wall h (64 cores)", "Raw output GB"]),
          "", f"Cost model: {COST_LO*1e6:.0f}-{COST_HI*1e6:.0f} us per point-level-step, "
              f"{PAR_EFF:.0%} parallel efficiency on one {NODE_CORES}-core node. "
              "Output is uncompressed netCDF; netCDF-4 deflate typically halves it.", ""]
    inp = inputs_gb(cfg)
    md += ["## Input data", "", table([[k, f"{v:.2f}"] for k, v in inp.items()], ["Item", "GB"]), ""]
    keep_inputs = inp["20CRv3 regional subsets (OPeNDAP, both events)"] + \
        inp["ERA5 regional subset (2005, 37 levels, 3-hourly)"] + inp["IMD 0.25 deg rainfall (1924, 2005)"]
    derived = 0.5   # daily precipitation on the IMD grid + surface diagnostics, all runs
    tiers = [
        ("Working set on the HPC during the runs", tout + sum(inp.values()) - inp["20CRv3 whole annual global files, if subsetting fails (1924 + 2005)"]),
        ("Archive: raw model output", tout),
        ("Archive: inputs needed to reproduce (driver subsets + IMD)", keep_inputs),
        ("Published: derived precipitation + scores (Zenodo)", derived),
        ("GitHub repository (code, namelists, scores, figures)", 0.05),
    ]
    rows = []
    for name, gb in tiers:
        gib = gb / 1.073741824
        rows.append([name, f"{gb:,.1f}"] + [f"${gib * p:,.2f}" for p in PRICES.values()])
    md += ["## Storage tiers and monthly cost if held in cloud object storage", "",
           table(rows, ["Tier", "GB"] + [f"{k} / month" for k in PRICES]), "",
           "On the project HPC node and the in-house 100 TB storage the marginal cost is zero; the cloud "
           "columns are the price of keeping the same bytes in Google Cloud Storage "
           "(us-central1 list price; egress to the internet is billed separately).", ""]
    text = "\n".join(md)
    print(text)
    if a.md:
        a.md.write_text("# Budget (generated by scripts/budget.py)\n\n" + text)


if __name__ == "__main__":
    main()
