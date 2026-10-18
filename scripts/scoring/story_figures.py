#!/usr/bin/env python3
"""Figures for the write-up, written to results/figures/story/.

    python scripts/scoring/story_figures.py --runs-root RUNS

  fig1_domains.png             the 12 km domain, the 3 km nests, terrain and scoring boxes
  fig2_<event>_synoptic.png    the driver's large-scale setting on the wettest observed day:
                               sea-level pressure, 850 hPa wind, column water vapour
  fig3_<event>_totals.png      event-total rainfall on the IMD grid: IMD, driver and every run,
                               each panel with its bias, pattern correlation and FSS
  fig4_<event>_native.png      the same on the 3 km model grids, with terrain contours
  fig5_<event>_daily.png       day by day over the scoring box: area mean and maximum
  fig6_scores.png              the scorecard as a heatmap (shading = closeness to perfect)
  fig7_santacruz.png           rain accumulated at Santacruz (Mumbai), 08:30 IST 26 July to
                               08:30 IST 27 July 2005, against the 944 mm observed there

Inputs are the ones scoring uses (data/daily, data/obs, data/drivers, results/scores.csv) plus
the model output under RUNS. A figure whose inputs are missing is skipped with a message.

Colours: WRF blue, RegCM orange, driver aqua (categorical slots 1-3, validated as a set for
colour-vision deficiency); 12 km dashed, 3 km solid; IMD black. Rainfall uses one blue ramp.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, G, ROOT, load_config  # noqa: E402
import metrics as M  # noqa: E402
from score_all import obs_for_event  # noqa: E402

INK, INK2, RULE = "#0b0b0b", "#52514e", "#d9d8d4"
COL = {"WRF": "#2a78d6", "RegCM": "#eb6834", "DRIVER": "#1baf7a", "IMD": INK}
LS = {"12km": (0, (5, 2)), "3km": "-", "DRIVER": (0, (1.5, 1.5))}
BLUES = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
         "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
RAIN_LEVELS = [0, 10, 25, 50, 100, 150, 200, 300, 400, 600, 800, 1000, 1500, 2000]
RAIN_CMAP = ListedColormap(["#ffffff"] + BLUES[:12])
RAIN_CMAP.set_over(BLUES[12])
RAIN_NORM = BoundaryNorm(RAIN_LEVELS, RAIN_CMAP.N)
SANTACRUZ = (19.0896, 72.8656)            # IMD Santacruz observatory, Mumbai
SANTACRUZ_MM = 944.0                      # 24 h to 08:30 IST 27 July 2005
CITIES = {"E1_kerala1924": [("Aluva", 10.11, 76.35)], "E2_mumbai2005": [("Mumbai", 19.08, 72.88)]}
plt.rcParams.update({"font.size": 8, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.titlesize": 9, "axes.titleweight": "bold",
                     "legend.frameon": False, "savefig.dpi": 200})


def say(msg):
    print(msg, flush=True)


def family(run):
    """'WRF_3km_ERA5' -> ('WRF', '3km', 'ERA5'); 'DRIVER_20CRv3' -> ('DRIVER', None, '20CRv3')."""
    p = run.split("_")
    return (p[0], None, p[1]) if p[0] == "DRIVER" else (p[0], p[1], p[2])


def label(run):
    m, r, d = family(run)
    return f"{d} (driver)" if m == "DRIVER" else f"{m} {r.replace('km', ' km')}"


def style(run):
    m, r, _ = family(run)
    return dict(color=COL[m], ls=LS["DRIVER" if m == "DRIVER" else r], lw=1.6,
                marker="o" if r == "3km" else ("s" if m == "DRIVER" else None), ms=3)


def box_line(ax, b, **kw):
    ax.plot([b["lon_min"], b["lon_max"], b["lon_max"], b["lon_min"], b["lon_min"]],
            [b["lat_min"], b["lat_min"], b["lat_max"], b["lat_max"], b["lat_min"]], **kw)


def windows(ev):
    s = datetime.fromisoformat(ev["score_start"])
    return s, s + timedelta(days=ev["score_ndays"])


def geo(runs, ev_name, drv, dom):
    f = runs / "wps" / f"{ev_name}_{drv}" / f"geo_em.{dom}.nc"
    if not f.exists():
        return None
    g = xr.open_dataset(f).isel(Time=0)
    return {k: g[v].values for k, v in (("lat", "XLAT_M"), ("lon", "XLONG_M"), ("hgt", "HGT_M"),
                                         ("land", "LANDMASK"))}


def coast(ax, lat, lon, land, lw=0.6):
    ax.contour(lon, lat, land.astype(float), levels=[0.5], colors=INK2, linewidths=lw)


def wrf_times(f):
    with xr.open_dataset(f, decode_times=False) as ds:
        t = ds["Times"].values
    txt = [x.decode() if isinstance(x, bytes) else "".join(c.decode() for c in np.atleast_1d(x)) for x in t]
    return [datetime.strptime(x, "%Y-%m-%d_%H:%M:%S") for x in txt]


def wrf_acc(d, dom, when):
    """Accumulated rain (mm) at each time in `when` on WRF domain `dom`, plus grid fields."""
    files = sorted(d.glob(f"wrfout_{dom}_*"))
    if not files:
        return None
    out, fields = {}, None
    for f in files:
        ts = wrf_times(f)
        need = [i for i, t in enumerate(ts) if t in when and t not in out]
        if not need and fields is not None:
            continue
        with xr.open_dataset(f, decode_times=False) as ds:
            if fields is None:
                fields = dict(lat=ds["XLAT"].values[0], lon=ds["XLONG"].values[0],
                              hgt=ds["HGT"].values[0] if "HGT" in ds else None,
                              land=ds["LANDMASK"].values[0] if "LANDMASK" in ds else None)
            for i in need:
                a = ds["RAINC"].values[i] + ds["RAINNC"].values[i]
                if "RAINSH" in ds:
                    a = a + ds["RAINSH"].values[i]
                out[ts[i]] = a.astype("float64")
    missing = [t for t in when if t not in out]
    if missing:
        raise ValueError(f"{d}/{dom}: output lacks {missing[0]}")
    return out, fields


def regcm_pr(d):
    files = sorted((d / "output").glob("*SHF*.nc"))
    if not files:
        return None
    ds = xr.open_mfdataset(files, combine="by_coords")
    return ds["pr"], ds["xlat"].values, ds["xlon"].values


def regcm_total(d, t0, t1):
    r = regcm_pr(d)
    if r is None:
        return None
    pr, lat, lon = r
    t = pr["time"].values.astype("datetime64[s]")
    sel = (t > np.datetime64(t0, "s")) & (t <= np.datetime64(t1, "s"))
    return (pr.values[sel].sum(0) * 3600.0), lat, lon


def scores_table():
    f = ROOT / "results" / "scores.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f)
    return {(r.event, r.run, r.metric): r.value for r in df.itertuples()}


def rain_colorbar(fig, mappable, axes, what):
    cb = fig.colorbar(mappable, ax=axes, shrink=0.85, pad=0.02, extend="max", ticks=RAIN_LEVELS[1:])
    cb.set_label(what)
    cb.outline.set_edgecolor(RULE)
    return cb


# ----------------------------------------------------------------------------- fig 1 ----
def fig_domains(cfg, runs, out):
    evs = list(cfg["events"].items())
    d01 = None
    for ev_name, ev in evs:
        d01 = d01 or geo(runs, ev_name, ev["drivers"][0], "d01")
    if d01 is None:
        return say("fig1: no geo_em.d01 under runs/wps, skipped")
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    hgt = np.where(d01["land"] > 0.5, d01["hgt"], np.nan)
    grays = ListedColormap(["#f3f2ef", "#dedcd6", "#c6c3ba", "#aaa69b", "#8c887d", "#6d6a61", "#4f4d46"])
    lv = [0, 100, 300, 600, 1000, 1500, 2500, 6000]
    ax.set_facecolor("#eef4fb")
    pc = ax.pcolormesh(d01["lon"], d01["lat"], hgt, cmap=grays, norm=BoundaryNorm(lv, grays.N), shading="nearest")
    coast(ax, d01["lat"], d01["lon"], d01["land"])
    for ev_name, ev in evs:
        drv = ev["drivers"][0]
        g2 = geo(runs, ev_name, drv, "d02")
        if g2 is not None:
            la, lo = g2["lat"], g2["lon"]
            ring = np.concatenate([np.c_[lo[0, :], la[0, :]], np.c_[lo[:, -1], la[:, -1]],
                                   np.c_[lo[-1, ::-1], la[-1, ::-1]], np.c_[lo[::-1, 0], la[::-1, 0]]])
            ax.plot(ring[:, 0], ring[:, 1], color=COL["WRF"], lw=1.4)
        r3 = regcm_pr(runs / "regcm" / f"{ev_name}_{drv}_03km")
        if r3 is not None:
            _, la, lo = r3
            ring = np.concatenate([np.c_[lo[0, :], la[0, :]], np.c_[lo[:, -1], la[:, -1]],
                                   np.c_[lo[-1, ::-1], la[-1, ::-1]], np.c_[lo[::-1, 0], la[::-1, 0]]])
            ax.plot(ring[:, 0], ring[:, 1], color=COL["RegCM"], lw=1.4, ls=(0, (5, 2)))
        box_line(ax, ev["score_box"], color=INK, lw=1.0, ls=(0, (2, 1.5)))
        for name, la_, lo_ in CITIES.get(ev_name, []):
            ax.plot(lo_, la_, "o", color=INK, ms=3)
            ax.annotate(name, (lo_, la_), xytext=(4, -2), textcoords="offset points", fontsize=7, color=INK)
        b = ev["score_box"]
        ax.annotate(ev_name.split("_")[0], (b["lon_max"], b["lat_max"]), xytext=(3, 2),
                    textcoords="offset points", fontsize=8, fontweight="bold", color=INK)
    ax.plot([], [], color=COL["WRF"], lw=1.4, label="WRF 3 km nest (d02)")
    ax.plot([], [], color=COL["RegCM"], lw=1.4, ls=(0, (5, 2)), label="RegCM5 3 km domain")
    ax.plot([], [], color=INK, lw=1.0, ls=(0, (2, 1.5)), label="scoring box")
    ax.legend(loc="lower left", fontsize=7)
    ax.set_aspect("equal")
    ax.set_xlabel("longitude (°E)")
    ax.set_ylabel("latitude (°N)")
    ax.set_title("12 km domain (WRF d01 = RegCM5 12 km) and 3 km domains")
    cb = fig.colorbar(pc, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label("terrain height (m)")
    fig.savefig(out / "fig1_domains.png", bbox_inches="tight")
    plt.close(fig)
    say("fig1 written")


# ----------------------------------------------------------------------------- fig 2 ----
def wettest_window(cfg, ev_name, ev):
    """The scoring day with the largest observed box-mean rainfall, as (start, end)."""
    files = sorted((DATA / "daily" / ev_name).glob("*.nc"))
    if not files:
        return None
    ref = xr.open_dataset(files[0])
    lat, lon = ref["lat"].values, ref["lon"].values
    o, labels = obs_for_event(cfg, ev, lat, lon)
    b = ev["score_box"]
    inbox = ((lat >= b["lat_min"]) & (lat <= b["lat_max"]))[:, None] & ((lon >= b["lon_min"]) & (lon <= b["lon_max"]))[None, :]
    mask = inbox & np.all(np.isfinite(o), axis=0)
    k = int(np.argmax([np.nanmean(np.where(mask, d, np.nan)) for d in o]))
    s = datetime.fromisoformat(ev["score_start"]) + timedelta(days=k)
    return s, s + timedelta(days=1)


def tcwv(ds):
    """Column water vapour (kg m-2) from pressure-level Q, counting only levels above the surface."""
    p = ds["plev"].values.astype("float64")
    order = np.argsort(p)                                        # top -> bottom
    p = p[order]
    q = ds["Q"].values[:, order]                                 # (time, plev, lat, lon)
    ps = ds["PSFC"].values[:, None]                              # (time, 1, lat, lon)
    pl, pu = p[1:][None, :, None, None], p[:-1][None, :, None, None]
    layer = 0.5 * (q[:, 1:] + q[:, :-1]) * (np.minimum(pl, ps) - pu).clip(min=0)
    return layer.sum(1) / G


def fig_synoptic(cfg, out):
    for ev_name, ev in cfg["events"].items():
        w = wettest_window(cfg, ev_name, ev)
        if w is None:
            say(f"fig2 {ev_name}: no daily files, skipped")
            continue
        t0, t1 = w
        drvs = [d for d in ev["drivers"] if (DATA / "drivers" / f"{ev_name}_{d}.nc").exists()]
        if not drvs:
            say(f"fig2 {ev_name}: no driver files, skipped")
            continue
        fig, axes = plt.subplots(1, len(drvs), figsize=(5.0 * len(drvs), 4.6), squeeze=False)
        for ax, d in zip(axes[0], drvs):
            ds = xr.open_dataset(DATA / "drivers" / f"{ev_name}_{d}.nc")
            tt = ds["time"].values.astype("datetime64[s]")
            sel = (tt >= np.datetime64(t0, "s")) & (tt <= np.datetime64(t1, "s"))
            sub = ds.isel(time=np.where(sel)[0])
            box = dict(lat=slice(0, 30), lon=slice(55, 95))
            sub = sub.sel(**box)
            lat, lon = sub["lat"].values, sub["lon"].values
            wv = tcwv(sub).mean(0)
            k850 = int(np.argmin(abs(sub["plev"].values - 85000.0)))
            u = sub["U"].values[:, k850].mean(0)
            v = sub["V"].values[:, k850].mean(0)
            slp = sub["PMSL"].values.mean(0) / 100.0
            lv = [20, 30, 40, 45, 50, 55, 60, 65, 70, 75]
            cm = ListedColormap(["#ffffff"] + BLUES[1:12:1][:len(lv) - 2])
            cm.set_over(BLUES[12])
            pc = ax.contourf(lon, lat, wv, levels=lv, cmap=cm, norm=BoundaryNorm(lv, cm.N), extend="max")
            cs = ax.contour(lon, lat, slp, levels=np.arange(np.floor(slp.min()), np.ceil(slp.max()) + 1, 2),
                            colors=INK2, linewidths=0.6)
            ax.clabel(cs, fmt="%d", fontsize=6)
            step = max(1, int(round(1.5 / abs(lon[1] - lon[0]))))
            qv = ax.quiver(lon[::step], lat[::step], u[::step, ::step], v[::step, ::step], color=INK,
                           scale=400, width=0.0028, headwidth=3.5)
            ax.quiverkey(qv, 0.86, 1.03, 15, "15 m/s", labelpos="W", fontproperties={"size": 7})
            ax.contour(lon, lat, sub["LANDSEA"].values, levels=[0.5], colors=INK, linewidths=0.5)
            box_line(ax, ev["score_box"], color="#e34948", lw=1.2)
            ax.set_aspect("equal")
            ax.set_title(f"{d}", loc="left")
            ax.set_xlabel("longitude (°E)")
            ax.set_ylabel("latitude (°N)")
        cb = fig.colorbar(pc, ax=axes[0], shrink=0.85, pad=0.02, extend="max")
        cb.set_label("column water vapour (kg m⁻²)")
        when = f"{t0:%d %b %Y %H} UTC to {t1:%d %b %H} UTC"
        fig.suptitle(f"{ev['title']}: wettest observed day ({when}), driver mean\n"
                     "shading: column water vapour; contours: sea-level pressure (hPa); arrows: 850 hPa wind",
                     fontsize=8)
        fig.savefig(out / f"fig2_{ev_name}_synoptic.png", bbox_inches="tight")
        plt.close(fig)
        say(f"fig2 {ev_name} written")


# ----------------------------------------------------------------------------- fig 3 ----
def fig_totals(cfg, runs, out, sc):
    thr = cfg["scoring"]["thresholds_mm_day"]
    tmid = thr[1] if len(thr) > 1 else thr[0]
    for ev_name, ev in cfg["events"].items():
        files = {f.stem: f for f in (DATA / "daily" / ev_name).glob("*.nc")}
        if not files:
            say(f"fig3 {ev_name}: no daily files, skipped")
            continue
        ref = xr.open_dataset(next(iter(files.values())))
        lat, lon = ref["lat"].values, ref["lon"].values
        o, _ = obs_for_event(cfg, ev, lat, lon)
        g1 = geo(runs, ev_name, ev["drivers"][0], "d01")
        cols = ["IMD", "DRIVER", "WRF_12km", "WRF_3km", "RegCM_12km", "RegCM_3km"]
        drvs = ev["drivers"]
        fig, axes = plt.subplots(len(drvs), len(cols), figsize=(2.25 * len(cols), 2.6 * len(drvs) + 0.4),
                                 squeeze=False, sharex=True, sharey=True)
        pc = None
        for i, d in enumerate(drvs):
            for j, c in enumerate(cols):
                ax = axes[i, j]
                run = "IMD" if c == "IMD" else (f"DRIVER_{d}" if c == "DRIVER" else f"{c}_{d}")
                if run == "IMD":
                    f = o.sum(0)
                elif run in files:
                    f = xr.open_dataset(files[run])["pr"].values.sum(0)
                else:
                    ax.axis("off")
                    continue
                pc = ax.pcolormesh(lon, lat, f, cmap=RAIN_CMAP, norm=RAIN_NORM, shading="nearest")
                if g1 is not None:
                    coast(ax, g1["lat"], g1["lon"], g1["land"], lw=0.5)
                box_line(ax, ev["score_box"], color=INK, lw=0.8, ls=(0, (2, 1.5)))
                ax.set_xlim(lon.min(), lon.max())
                ax.set_ylim(lat.min(), lat.max())
                ax.set_aspect("equal")
                ax.set_title("IMD (observed)" if run == "IMD" else label(run), fontsize=8)
                if sc is not None and run != "IMD":
                    b, r, f_ = (sc.get((ev_name, run, m), np.nan) for m in
                                ("bias_pct", "corr_total", f"FSS_{tmid:g}mm_5pt"))
                    ax.text(0.03, 0.03, f"bias {b:+.0f}%\nr {r:.2f}\nFSS {f_:.2f}", transform=ax.transAxes,
                            fontsize=6.5, va="bottom", color=INK,
                            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=RULE, lw=0.5))
            axes[i, 0].set_ylabel(f"driven by {d}\nlatitude (°N)")
        for ax in axes[-1]:
            ax.set_xlabel("longitude (°E)")
        rain_colorbar(fig, pc, axes, f"event total (mm, {ev['score_ndays']} days)")
        s, e = windows(ev)
        fig.suptitle(f"{ev['title']}: rainfall {s:%d %b} to {e:%d %b %Y} (08:30 IST) on the IMD 0.25° grid\n"
                     f"scores inside the dashed box; FSS at ≥{tmid:g} mm/day, 5-point neighbourhood", fontsize=8)
        fig.savefig(out / f"fig3_{ev_name}_totals.png", bbox_inches="tight")
        plt.close(fig)
        say(f"fig3 {ev_name} written")


# ----------------------------------------------------------------------------- fig 4 ----
def fig_native(cfg, runs, out):
    for ev_name, ev in cfg["events"].items():
        t0, t1 = windows(ev)
        panels = []
        geo2 = None
        for d in ev["drivers"]:
            w = wrf_acc(runs / "wrf" / f"{ev_name}_{d}", "d02", [t0, t1])
            if w is not None:
                acc, fl = w
                panels.append((f"WRF 3 km, {d}", fl["lat"], fl["lon"], acc[t1] - acc[t0]))
                geo2 = geo2 or fl
            r = regcm_total(runs / "regcm" / f"{ev_name}_{d}_03km", t0, t1)
            if r is not None:
                tot, la, lo = r
                panels.append((f"RegCM5 3 km, {d}", la, lo, tot))
        if not panels or geo2 is None:
            say(f"fig4 {ev_name}: no 3 km output, skipped")
            continue
        imd = xr.open_dataset(DATA / "obs" / f"imd_rain_{t0.year}.nc")["rain"]
        fwd = cfg["observations"]["imd_label"] == "forward"
        days = [(t0 + timedelta(days=k + (0 if fwd else 1))).date() for k in range(ev["score_ndays"])]
        io = imd.sel(time=[np.datetime64(x) for x in days]).sum("time", min_count=len(days))
        la2, lo2 = geo2["lat"], geo2["lon"]
        io = io.sel(lat=slice(la2.min(), la2.max()), lon=slice(lo2.min(), lo2.max()))
        panels = [("IMD (observed, 0.25°)", io["lat"].values, io["lon"].values, io.values)] + panels
        n = len(panels)
        fig, axes = plt.subplots(1, n, figsize=(2.7 * n, 3.3), squeeze=False, sharex=True, sharey=True)
        for ax, (name, la, lo, f) in zip(axes[0], panels):
            pc = ax.pcolormesh(lo, la, f, cmap=RAIN_CMAP, norm=RAIN_NORM, shading="nearest")
            if geo2["hgt"] is not None:
                ax.contour(lo2, la2, geo2["hgt"], levels=[500, 1000], colors=INK2, linewidths=0.4,
                           linestyles=["--", "-"])
            if geo2["land"] is not None:
                coast(ax, la2, lo2, geo2["land"], lw=0.5)
            box_line(ax, ev["score_box"], color=INK, lw=0.8, ls=(0, (2, 1.5)))
            ax.set_xlim(lo2.min(), lo2.max())
            ax.set_ylim(la2.min(), la2.max())
            ax.set_aspect("equal")
            ax.set_title(name, fontsize=8)
            ax.set_xlabel("longitude (°E)")
        axes[0, 0].set_ylabel("latitude (°N)")
        rain_colorbar(fig, pc, axes, f"event total (mm, {ev['score_ndays']} days)")
        fig.suptitle(f"{ev['title']}: event total on the 3 km model grids "
                     "(grey contours: WRF terrain 500 m dashed, 1000 m solid)", fontsize=8)
        fig.savefig(out / f"fig4_{ev_name}_native.png", bbox_inches="tight")
        plt.close(fig)
        say(f"fig4 {ev_name} written")


# ----------------------------------------------------------------------------- fig 5 ----
def fig_daily(cfg, out):
    for ev_name, ev in cfg["events"].items():
        files = {f.stem: f for f in (DATA / "daily" / ev_name).glob("*.nc")}
        if not files:
            say(f"fig5 {ev_name}: no daily files, skipped")
            continue
        ref = xr.open_dataset(next(iter(files.values())))
        lat, lon = ref["lat"].values, ref["lon"].values
        o, labels = obs_for_event(cfg, ev, lat, lon)
        b = ev["score_box"]
        inbox = ((lat >= b["lat_min"]) & (lat <= b["lat_max"]))[:, None] & ((lon >= b["lon_min"]) & (lon <= b["lon_max"]))[None, :]
        mask = inbox & np.all(np.isfinite(o), axis=0)
        w = M.area_weights(lat, lon)

        def stats(f):
            mean = [float(np.sum(np.where(mask, x, 0) * w) / np.sum(np.where(mask, w, 0))) for x in f]
            mx = [float(np.nanmax(np.where(mask, x, np.nan))) for x in f]
            return mean, mx

        x = np.arange(len(labels))
        drvs = ev["drivers"]
        fig, axes = plt.subplots(2, len(drvs), figsize=(4.6 * len(drvs), 5.2), squeeze=False, sharex=True)
        om, ox = stats(o)
        for j, d in enumerate(drvs):
            for i, (which, obsv) in enumerate((("box mean", om), ("box maximum", ox))):
                ax = axes[i, j]
                ax.plot(x, obsv, color=COL["IMD"], lw=2.4, marker="o", ms=4, label="IMD (observed)", zorder=5)
                for run in [f"DRIVER_{d}", f"WRF_12km_{d}", f"WRF_3km_{d}", f"RegCM_12km_{d}", f"RegCM_3km_{d}"]:
                    if run not in files:
                        continue
                    mm, mxv = stats(xr.open_dataset(files[run])["pr"].values)
                    name = "driver reanalysis" if run.startswith("DRIVER") else label(run)
                    ax.plot(x, mm if i == 0 else mxv, label=name, **style(run))
                ax.set_ylabel(f"{which} (mm/day)")
                ax.grid(axis="y", color=RULE, lw=0.5)
                ax.spines[["top", "right"]].set_visible(False)
                ax.set_ylim(bottom=0)
                if i == 0:
                    ax.set_title(f"driven by {d}", loc="left")
            axes[1, j].set_xticks(x, [f"{t:%d %b}" for t in labels], rotation=0)
            axes[1, j].set_xlabel("IMD day (24 h ending 08:30 IST)")
        axes[0, -1].legend(fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1.0))
        fig.suptitle(f"{ev['title']}: daily rainfall over the scoring box", fontsize=9)
        fig.savefig(out / f"fig5_{ev_name}_daily.png", bbox_inches="tight")
        plt.close(fig)
        say(f"fig5 {ev_name} written")


# ----------------------------------------------------------------------------- fig 6 ----
def fig_scores(cfg, out):
    f = ROOT / "results" / "scores.csv"
    if not f.exists():
        return say("fig6: no results/scores.csv, skipped")
    df = pd.read_csv(f)
    thr = cfg["scoring"]["thresholds_mm_day"]
    mets = [("bias_pct", "bias %", lambda v: 1 - min(abs(v) / 100, 1)),
            ("corr_total", "pattern r", lambda v: max(v, 0)),
            ("peak_ratio", "peak ratio", lambda v: 1 - min(abs(1 - v), 1)),
            ("maxloc_err_km", "peak loc. err km", lambda v: 1 - min(v / 300, 1))]
    mets += [(f"FSS_{t:g}mm_5pt", f"FSS ≥{t:g}", lambda v: v) for t in thr]
    mets += [(f"SAL_{k}", f"SAL {k}", lambda v: 1 - min(abs(v) / 2, 1)) for k in "SAL"]
    evs = [e for e in cfg["events"] if (df.event == e).any()]
    order = lambda r: (family(r)[2], ["DRIVER", "WRF", "RegCM"].index(family(r)[0]), family(r)[1] or "")
    heights = [len([r for r in df[df.event == e].run.unique() if r != "IMD"]) for e in evs]
    fig, axes = plt.subplots(len(evs), 1, figsize=(8.2, 0.34 * sum(heights) + 1.6 * len(evs)),
                             gridspec_kw=dict(height_ratios=heights), squeeze=False)
    cm = ListedColormap(BLUES[:12])
    for ax, e in zip(axes[:, 0], evs):
        runs = sorted([r for r in df[df.event == e].run.unique() if r != "IMD"], key=order)
        tab = df[df.event == e].pivot(index="run", columns="metric", values="value")
        raw = np.array([[tab.loc[r, m] if m in tab.columns else np.nan for m, _, _ in mets] for r in runs])
        good = np.array([[fn(v) if np.isfinite(v) else np.nan for v, (_, _, fn) in zip(row, mets)] for row in raw])
        ax.imshow(good, cmap=cm, vmin=0, vmax=1, aspect="auto")
        for i in range(len(runs)):
            for j in range(len(mets)):
                v = raw[i, j]
                if np.isfinite(v):
                    txt = f"{v:+.0f}" if mets[j][0] == "bias_pct" else (f"{v:.0f}" if "km" in mets[j][0] else f"{v:.2f}")
                    ax.text(j, i, txt, ha="center", va="center", fontsize=6.5,
                            color="white" if good[i, j] > 0.62 else INK)
        ax.set_yticks(range(len(runs)), [f"{label(r)}  ({family(r)[2]})" if family(r)[0] != "DRIVER" else label(r)
                                          for r in runs], fontsize=7)
        ax.set_xticks(range(len(mets)), [n for _, n, _ in mets], fontsize=7, rotation=30, ha="right")
        ax.set_title(cfg["events"][e]["title"], loc="left", fontsize=8)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_xticks(np.arange(-0.5, len(mets)), minor=True)
        ax.set_yticks(np.arange(-0.5, len(runs)), minor=True)
        ax.grid(which="minor", color="white", lw=1.5)
        ax.tick_params(which="minor", length=0)
    fig.text(0.01, 0.005, "Shading: closeness to a perfect score (darker = better), from the value printed in each cell.",
             fontsize=7, color=INK2)
    fig.tight_layout()
    fig.savefig(out / "fig6_scores.png", bbox_inches="tight")
    plt.close(fig)
    say("fig6 written")


# ----------------------------------------------------------------------------- fig 7 ----
def nearest(lat, lon, p):
    d2 = (lat - p[0]) ** 2 + ((lon - p[1]) * np.cos(np.radians(p[0]))) ** 2
    return np.unravel_index(np.argmin(d2), lat.shape)


def within(lat, lon, p, km):
    d = 6371.0 * np.radians(np.hypot(lat - p[0], (lon - p[1]) * np.cos(np.radians(p[0]))))
    return d <= km


def fig_santacruz(cfg, runs, out):
    ev_name = "E2_mumbai2005"
    if ev_name not in cfg["events"]:
        return
    ev = cfg["events"][ev_name]
    t0, t1 = datetime(2005, 7, 26, 3), datetime(2005, 7, 27, 3)
    hours = [t0 + timedelta(hours=h) for h in range(25)]
    xh = np.arange(25)
    drvs = ev["drivers"]
    fig, axes = plt.subplots(1, len(drvs), figsize=(4.8 * len(drvs), 3.8), squeeze=False, sharey=True)
    any_line = False
    for ax, d in zip(axes[0], drvs):
        for dom, res in (("d01", "12km"), ("d02", "3km")):
            w = wrf_acc(runs / "wrf" / f"{ev_name}_{d}", dom, hours)
            if w is None:
                continue
            acc, fl = w
            j = nearest(fl["lat"], fl["lon"], SANTACRUZ)
            ser = [acc[t][j] - acc[t0][j] for t in hours]
            near = within(fl["lat"], fl["lon"], SANTACRUZ, 50)
            mx = float(np.max((acc[t1] - acc[t0])[near]))
            run = f"WRF_{res}_{d}"
            ax.plot(xh, ser, label=f"{label(run)} (max ≤50 km: {mx:.0f})", **{**style(run), "marker": None})
            any_line = True
        for res in ("12km", "03km"):
            r = regcm_pr(runs / "regcm" / f"{ev_name}_{d}_{res}")
            if r is None:
                continue
            pr, la, lo = r
            t = pr["time"].values.astype("datetime64[s]")
            sel = (t > np.datetime64(t0, "s")) & (t <= np.datetime64(t1, "s"))
            tt = t[sel]
            p = pr.values[sel] * 3600.0
            j = nearest(la, lo, SANTACRUZ)
            cum = np.concatenate([[0.0], np.cumsum(p[:, j[0], j[1]])])
            xs = np.concatenate([[0.0], (tt - np.datetime64(t0, "s")).astype(float) / 3600.0])
            mx = float(p.sum(0)[within(la, lo, SANTACRUZ, 50)].max())
            run = f"RegCM_{res.lstrip('0')}_{d}"
            ax.plot(xs, cum, label=f"{label(run)} (max ≤50 km: {mx:.0f})", **{**style(run), "marker": None})
            any_line = True
        pf = DATA / "drivers" / f"{ev_name}_{d}_precip.nc"
        if pf.exists():
            ds = xr.open_dataset(pf)
            ih = int(ds.attrs["interval_hours"])
            pr = ds["pr"].sel(lat=SANTACRUZ[0], lon=SANTACRUZ[1], method="nearest")
            t = pr["time"].values.astype("datetime64[s]")
            sel = (t > np.datetime64(t0, "s")) & (t <= np.datetime64(t1, "s"))
            cum = np.concatenate([[0.0], np.cumsum(pr.values[sel] * ih * 3600.0)])
            xs = np.concatenate([[0.0], (t[sel] - np.datetime64(t0, "s")).astype(float) / 3600.0])
            ax.plot(xs, cum, label=label(f"DRIVER_{d}"), **{**style(f"DRIVER_{d}"), "marker": None})
        ax.axhline(SANTACRUZ_MM, color=INK, lw=1.2)
        ax.text(24, SANTACRUZ_MM + 15, f"observed at Santacruz: {SANTACRUZ_MM:.0f} mm", fontsize=7,
                color=INK, ha="right")
        ax.set_title(f"driven by {d}", loc="left")
        ist = [t0 + timedelta(hours=h, minutes=330) for h in range(0, 25, 3)]
        ax.set_xticks(range(0, 25, 3), [f"{t:%H:%M}" for t in ist])
        ax.set_xlabel("IST, 26 July 08:30 to 27 July 08:30")
        ax.grid(axis="y", color=RULE, lw=0.5)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(fontsize=6.5, loc="upper left", bbox_to_anchor=(0, -0.2), ncol=2)
    if not any_line:
        plt.close(fig)
        return say("fig7: no E2 model output, skipped")
    axes[0, 0].set_ylabel("rain since 08:30 IST 26 July (mm)")
    axes[0, 0].set_ylim(0, max(1100, axes[0, 0].get_ylim()[1]))
    fig.suptitle("Mumbai, 26 July 2005: rain accumulated at the grid point nearest Santacruz", fontsize=9)
    fig.savefig(out / "fig7_santacruz.png", bbox_inches="tight")
    plt.close(fig)
    say("fig7 written")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", type=Path, required=True)
    a = ap.parse_args()
    cfg = load_config()
    out = ROOT / "results" / "figures" / "story"
    out.mkdir(parents=True, exist_ok=True)
    sc = scores_table()
    for name, fn in (("fig1", lambda: fig_domains(cfg, a.runs_root, out)),
                     ("fig2", lambda: fig_synoptic(cfg, out)),
                     ("fig3", lambda: fig_totals(cfg, a.runs_root, out, sc)),
                     ("fig4", lambda: fig_native(cfg, a.runs_root, out)),
                     ("fig5", lambda: fig_daily(cfg, out)),
                     ("fig6", lambda: fig_scores(cfg, out)),
                     ("fig7", lambda: fig_santacruz(cfg, a.runs_root, out))):
        try:
            fn()
        except Exception as e:                       # one broken figure must not stop the others
            say(f"{name} FAILED: {type(e).__name__}: {e}")
    say(f"figures in {out}")


if __name__ == "__main__":
    main()
