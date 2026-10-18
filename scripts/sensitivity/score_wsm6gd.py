#!/usr/bin/env python3
"""POST-HOC, EXPLORATORY: score the WSM6 + Grell-Devenyi rerun of E2 with ERA5 against the
baseline (Thompson + Grell-Freitas). Not part of H1-H5 and never written into
results/scores.csv, SCORECARD.md or HYPOTHESES.md.

    python scripts/sensitivity/score_wsm6gd.py --runs-root RUNS

Inputs : RUNS/wrf/E2_mumbai2005_ERA5_wsm6gd/wrfout_d0*  (scripts/sensitivity/wsm6gd.sh)
         RUNS/wrf/E2_mumbai2005_ERA5/wrfout_d0*          (baseline, for the Santacruz series)
         data/daily/E2_mumbai2005/*.nc, data/obs           (as for score_all.py)
Outputs: data/sensitivity/E2_mumbai2005/WRF_<res>_ERA5_wsm6gd.nc  (same form as data/daily)
         results/sensitivity/SENSITIVITY.md   scores of baseline and variant side by side
         results/sensitivity/fig_wsm6gd.png   daily box maximum and Santacruz accumulation

Same extraction (extract_precip.py), same remap, same observations, same metrics as the
pre-registered scoring, so the two rows of each pair differ only by the physics.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import xarray as xr

HERE = Path(__file__).resolve()
for p in (HERE.parents[1], HERE.parents[1] / "scoring", HERE.parents[1] / "postprocess"):
    sys.path.insert(0, str(p))
from common import DATA, ROOT, load_config  # noqa: E402
import metrics as M  # noqa: E402
import check_imd_convention  # noqa: E402
from score_all import obs_for_event, score_run  # noqa: E402
from extract_precip import target_grid, windows, wrf_daily  # noqa: E402
from remap import Remapper  # noqa: E402
import story_figures as SF  # noqa: E402  (shared styles and the Santacruz helpers)
import matplotlib.pyplot as plt  # noqa: E402

EV, DRV, TAG = "E2_mumbai2005", "ERA5", "wsm6gd"
VARIANT_COL = "#eda100"     # categorical slot 4; validated against WRF blue (CVD dE >= 29.6);
                            # below 3:1 on white, so it always has markers and a legend entry
PHYS = {"base": "Thompson + Grell-Freitas (baseline)", TAG: "WSM6 + Grell-Devenyi (post hoc)"}
METRICS = [("bias_pct", "bias %", "{:+.0f}"), ("corr_total", "pattern r", "{:.2f}"),
           ("peak_ratio", "peak ratio", "{:.2f}"), ("maxloc_err_km", "peak loc. err km", "{:.0f}"),
           ("FSS_64.5mm_5pt", "FSS >=64.5", "{:.2f}"), ("FSS_115.6mm_5pt", "FSS >=115.6", "{:.2f}"),
           ("FSS_204.5mm_5pt", "FSS >=204.5", "{:.2f}")]


def extract(runs, cfg):
    ev = cfg["events"][EV]
    wins, (tla, tlo) = windows(ev), target_grid(ev)
    out = DATA / "sensitivity" / EV
    out.mkdir(parents=True, exist_ok=True)
    d = runs / "wrf" / f"{EV}_{DRV}_{TAG}"
    if not (d / "rsl.error.0000").exists() or b"SUCCESS COMPLETE WRF" not in (d / "rsl.error.0000").read_bytes():
        sys.exit(f"{d}: the variant run has not finished (scripts/sensitivity/wsm6gd.sh)")
    made = {}
    for dom, res in (("d01", "12km"), ("d02", "3km")):
        daily, lat, lon, dx = wrf_daily(list(d.glob(f"wrfout_{dom}_*")), wins)
        rm = Remapper(lat, lon, tla, tlo, src_dx_km=dx)
        field = np.stack([rm(x) for x in daily])
        name = f"WRF_{res}_{DRV}_{TAG}"
        xr.DataArray(field.astype("float32"), dims=("day", "lat", "lon"),
                     coords={"day": np.array([s for s, _ in wins], dtype="datetime64[s]"), "lat": tla, "lon": tlo},
                     name="pr", attrs={"units": "mm/day", "window": "24 h from the 'day' time (03 UTC)",
                                       "source_dx_km": dx, "remap_subsamples": rm.k,
                                       "note": "post-hoc sensitivity run, not part of H1-H5"}
                     ).to_netcdf(out / f"{name}.nc")
        made[res] = out / f"{name}.nc"
        print(f"{name}: dx={dx:.1f} km, box max {np.nanmax(field):.0f} mm/day")
    return made


def santacruz(run_dir, dom):
    """Accumulation at the grid point nearest Santacruz, 03 UTC 26 to 03 UTC 27 July (hourly),
    and the largest 24 h total within 50 km."""
    t0, t1 = datetime(2005, 7, 26, 3), datetime(2005, 7, 27, 3)
    hours = [t0 + timedelta(hours=h) for h in range(25)]
    w = SF.wrf_acc(run_dir, dom, hours)
    if w is None:
        return None
    acc, fl = w
    j = SF.nearest(fl["lat"], fl["lon"], SF.SANTACRUZ)
    ser = np.array([acc[t][j] - acc[t0][j] for t in hours])
    mx = float(np.max((acc[t1] - acc[t0])[SF.within(fl["lat"], fl["lon"], SF.SANTACRUZ, 50)]))
    return ser, mx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", type=Path, required=True)
    a = ap.parse_args()
    if check_imd_convention.main() != 0:
        sys.exit("IMD date-label check failed: fix observations.imd_label in config/experiment.yaml")
    cfg = load_config()
    ev, sc = cfg["events"][EV], cfg["scoring"]
    made = extract(a.runs_root, cfg)
    files = {("base", res): DATA / "daily" / EV / f"WRF_{res}_{DRV}.nc" for res in ("12km", "3km")}
    files.update({(TAG, res): f for res, f in made.items()})
    for k, f in files.items():
        if not f.exists():
            sys.exit(f"missing {f} (run scripts/postprocess/extract_precip.py {EV} first)")

    ref = xr.open_dataset(files[(TAG, "12km")])
    lat, lon = ref["lat"].values, ref["lon"].values
    o, labels = obs_for_event(cfg, ev, lat, lon)
    b = ev["score_box"]
    inbox = ((lat >= b["lat_min"]) & (lat <= b["lat_max"]))[:, None] & ((lon >= b["lon_min"]) & (lon <= b["lon_max"]))[None, :]
    mask = inbox & np.all(np.isfinite(o), axis=0)
    w = M.area_weights(lat, lon)
    kday = int(np.argmax([np.nanmean(np.where(mask, x, np.nan)) for x in o]))     # the cloudburst day

    def daily_stats(f):
        mean = [float(np.sum(np.where(mask, x, 0) * w) / np.sum(np.where(mask, w, 0))) for x in f]
        mx = [float(np.nanmax(np.where(mask, x, np.nan))) for x in f]
        return mean, mx

    rows, series = {}, {}
    for (phys, res), f in files.items():
        m = xr.open_dataset(f)["pr"].values.astype("float64")
        rows[(phys, res)] = score_run(m, o, mask, w, lat, lon, sc["thresholds_mm_day"], sc["fss_window_points"])
        series[(phys, res)] = daily_stats(m)
        d = a.runs_root / "wrf" / (f"{EV}_{DRV}" if phys == "base" else f"{EV}_{DRV}_{TAG}")
        s = santacruz(d, "d01" if res == "12km" else "d02")
        rows[(phys, res)]["santacruz_mm"] = s[0][-1] if s else np.nan
        rows[(phys, res)]["santacruz_max50_mm"] = s[1] if s else np.nan
        rows[(phys, res)]["day_boxmean_mm"] = series[(phys, res)][0][kday]
        rows[(phys, res)]["day_boxmax_mm"] = series[(phys, res)][1][kday]
        series[(phys, res)] += (s,)
    om, ox = daily_stats(o)

    # ---- table
    useful = {t: M.fss_useful(o, mask, t) for t in sc["thresholds_mm_day"]}
    day = f"{labels[kday]:%d %b}"
    head = ["run"] + [n for _, n, _ in METRICS] + [f"box mean {day}", f"box max {day}",
                                                    "Santacruz 24 h", "max within 50 km"]
    lines = ["# Post-hoc physics sensitivity, E2 Mumbai 2005, ERA5-driven WRF",
             "",
             "**Exploratory and post hoc: not part of the pre-registered criteria H1-H5 "
             "(docs/metrics.md), which are judged on the baseline runs only.**",
             "",
             "Baseline: Thompson (mp_physics=8) + Grell-Freitas (cu_physics=3) at 12 km, no cumulus "
             "scheme at 3 km. Variant: WSM6 (6) + Grell-Devenyi (93) at 12 km, none at 3 km, as in "
             "Kumar et al. (2008). Everything else identical; both schemes change together.",
             "",
             "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines.append("| IMD (observed) | " + " | ".join("" for _ in METRICS) +
                 f" | {om[kday]:.0f} | {ox[kday]:.0f} | {SF.SANTACRUZ_MM:.0f} (station) | |")
    for res in ("12km", "3km"):
        for phys in ("base", TAG):
            r = rows[(phys, res)]
            cells = [fmt.format(r[k]) if np.isfinite(r.get(k, np.nan)) else "" for k, _, fmt in METRICS]
            cells += [f"{r['day_boxmean_mm']:.0f}", f"{r['day_boxmax_mm']:.0f}",
                      f"{r['santacruz_mm']:.0f}", f"{r['santacruz_max50_mm']:.0f}"]
            lines.append(f"| WRF {res.replace('km', ' km')}, {PHYS[phys]} | " + " | ".join(cells) + " |")
    lines += ["", "FSS useful levels: " + ", ".join(f"{t:g} mm: {u:.2f}" for t, u in useful.items()),
              f"Day columns: IMD day {day} (24 h ending 08:30 IST), the wettest observed day. "
              "Santacruz: 08:30 IST 26 July to 08:30 IST 27 July at the model grid point nearest the "
              "observatory, and the largest 24 h total within 50 km of it."]
    res_dir = ROOT / "results" / "sensitivity"
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "SENSITIVITY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    # ---- figure: daily box maximum | Santacruz accumulation
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.9))
    x = np.arange(len(labels))
    ax1.plot(x, ox, color=SF.INK, lw=2.4, marker="o", ms=4, label="IMD (observed)", zorder=5)
    for res in ("12km", "3km"):
        for phys in ("base", TAG):
            col = SF.COL["WRF"] if phys == "base" else VARIANT_COL
            ls = SF.LS[res]
            mk = ("o" if phys == "base" else "s") if res == "3km" else (None if phys == "base" else "s")
            lab = f"WRF {res.replace('km', ' km')}, {PHYS[phys]}"
            ax1.plot(x, series[(phys, res)][1], color=col, ls=ls, lw=1.6, marker=mk, ms=3.5, label=lab)
            s = series[(phys, res)][2]
            if s is not None:
                ax2.plot(np.arange(25), s[0], color=col, ls=ls, lw=1.6, marker=mk, ms=3, markevery=3,
                         label=f"{lab} (max ≤50 km: {s[1]:.0f})")
    ax1.set_xticks(x, [f"{t:%d %b}" for t in labels])
    ax1.set_xlabel("IMD day (24 h ending 08:30 IST)")
    ax1.set_ylabel("box maximum (mm/day)")
    ax1.set_title("scoring box, daily maximum", loc="left")
    ax1.set_ylim(bottom=0)
    ax2.axhline(SF.SANTACRUZ_MM, color=SF.INK, lw=1.2)
    ax2.text(24, SF.SANTACRUZ_MM + 15, f"observed at Santacruz: {SF.SANTACRUZ_MM:.0f} mm", fontsize=7, ha="right")
    t0 = datetime(2005, 7, 26, 3)
    ax2.set_xticks(range(0, 25, 3), [f"{t0 + timedelta(hours=h, minutes=330):%H:%M}" for h in range(0, 25, 3)])
    ax2.set_xlabel("IST, 26 July 08:30 to 27 July 08:30")
    ax2.set_ylabel("rain since 08:30 IST 26 July (mm)")
    ax2.set_title("grid point nearest Santacruz", loc="left")
    ax2.set_ylim(0, max(1100, ax2.get_ylim()[1]))
    for ax in (ax1, ax2):
        ax.grid(axis="y", color=SF.RULE, lw=0.5)
        ax.spines[["top", "right"]].set_visible(False)
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    fig.legend(h1[:1] + h2, l1[:1] + l2, fontsize=6.5, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=2)
    fig.suptitle("Mumbai 2005, ERA5-driven WRF: baseline physics against WSM6 + Grell-Devenyi "
                 "(post-hoc sensitivity, not part of H1-H5)", fontsize=9)
    fig.savefig(res_dir / "fig_wsm6gd.png", bbox_inches="tight")
    plt.close(fig)
    print(f"written: {res_dir / 'SENSITIVITY.md'}, {res_dir / 'fig_wsm6gd.png'}")


if __name__ == "__main__":
    main()
