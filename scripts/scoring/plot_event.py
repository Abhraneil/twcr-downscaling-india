#!/usr/bin/env python3
"""Figures for each event: event-total maps (IMD and every run) and FSS against scale.

    python scripts/scoring/plot_event.py
Writes results/figures/<event>_totals.png and <event>_fss.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ROOT, load_config  # noqa: E402
from score_all import obs_for_event  # noqa: E402

ORDER = ["DRIVER", "WRF_12km", "WRF_3km", "RegCM_12km", "RegCM_3km"]


def main():
    cfg = load_config()
    figdir = ROOT / "results" / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    scores = pd.read_csv(ROOT / "results" / "scores.csv") if (ROOT / "results/scores.csv").exists() else None
    for ev_name, ev in cfg["events"].items():
        files = {f.stem: f for f in (DATA / "daily" / ev_name).glob("*.nc")}
        if not files:
            continue
        runs = sorted(files, key=lambda r: (r.split("_")[-1], next((i for i, p in enumerate(ORDER) if r.startswith(p)), 9)))
        ref = xr.open_dataset(files[runs[0]])
        lat, lon = ref["lat"].values, ref["lon"].values
        o, _ = obs_for_event(cfg, ev, lat, lon)
        fields = [("IMD", o.sum(0))] + [(r, xr.open_dataset(files[r])["pr"].values.sum(0)) for r in runs]
        vmax = np.nanpercentile(fields[0][1], 99.5)
        n = len(fields)
        ncol = min(4, n)
        nrow = int(np.ceil(n / ncol))
        fig, axes = plt.subplots(nrow, ncol, figsize=(3.4 * ncol, 3.6 * nrow), squeeze=False)
        b = ev["score_box"]
        for ax, (name, f) in zip(axes.flat, fields):
            f = np.where(np.isfinite(o.sum(0)), f, np.nan)   # IMD land mask
            pc = ax.pcolormesh(lon, lat, f, vmin=0, vmax=vmax, cmap="YlGnBu", shading="nearest")
            ax.plot([b["lon_min"], b["lon_max"], b["lon_max"], b["lon_min"], b["lon_min"]],
                    [b["lat_min"], b["lat_min"], b["lat_max"], b["lat_max"], b["lat_min"]], "k--", lw=0.8)
            ax.set_title(name, fontsize=9)
            ax.set_aspect("equal")
            ax.tick_params(labelsize=7)
        for ax in axes.flat[n:]:
            ax.axis("off")
        fig.colorbar(pc, ax=axes, shrink=0.8, label=f"event total (mm, {ev['score_ndays']} days)")
        fig.suptitle(ev["title"], fontsize=10)
        fig.savefig(figdir / f"{ev_name}_totals.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        if scores is None:
            continue
        s = scores[(scores.event == ev_name) & scores.metric.str.match(r"^FSS_")]
        thr = cfg["scoring"]["thresholds_mm_day"]
        fig, axes = plt.subplots(1, len(thr), figsize=(4 * len(thr), 3.2), sharey=True)
        for ax, t in zip(np.atleast_1d(axes), thr):
            for r in runs:
                g = s[(s.run == r) & s.metric.str.startswith(f"FSS_{t:g}mm_")]
                if g.empty:
                    continue
                n_pt = g.metric.str.extract(r"_(\d+)pt$")[0].astype(int) * 0.25
                ax.plot(n_pt, g.value, marker="o", lw=1, label=r,
                        ls="--" if r.startswith("DRIVER") else "-")
            ax.set_title(f">= {t:g} mm/day", fontsize=9)
            ax.set_xlabel("neighbourhood (deg)")
        np.atleast_1d(axes)[0].set_ylabel("FSS")
        np.atleast_1d(axes)[-1].legend(fontsize=6)
        fig.savefig(figdir / f"{ev_name}_fss.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"figures for {ev_name} written")


if __name__ == "__main__":
    main()
