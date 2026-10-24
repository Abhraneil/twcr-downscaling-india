#!/usr/bin/env python3
"""Mumbai, 26 July 2005: the figures of Litta et al. (2007, Meteorol. Appl. 14:291-295) for our runs.

    python scripts/scoring/mumbai_figures.py --runs-root RUNS     (also run by story_figures.py)

  fig8_E2_stations.png  24 h rain to 08:30 IST 27 July around Mumbai on the IMD 0.25 deg grid and
                        the 3 km model grids, with the gauge totals (Litta Fig. 1) as dots
  fig9_E2_3hourly.png   rain accumulated since 06 UTC 26 July at Santacruz and Colaba every 3 h:
                        the gauges (Litta Fig. 2) and the nearest grid point of every run
  fig10_E2_500hPa.png   500 hPa streamlines and relative vorticity at 06, 09, 12, 15 UTC 26 July
                        (Litta Fig. 7: every 2 h, 06-16 UTC): ERA5 and the ERA5-driven WRF 3 km runs
  fig11_E2_column.png   above Santacruz, 00 UTC 26 to 06 UTC 27 July: relative humidity, vertical
                        velocity and wind (Litta analysed these fields but did not show them)

Litta Fig. 3 (domains) is our fig 1; their Fig. 5 (TRMM 3B42 rain) has no counterpart here: IMD
gauge-based grids are used throughout. Runs started on 25 July are the post-hoc runs of the
config (post_hoc_runs), outside the criteria H1-H5.

fig 10 and fig 11 need the full hourly wrfout files (U, V, W, T, P, PB, QVAPOR); the slim archive
keeps only the rain, so there they are skipped with a message.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import xarray as xr
from matplotlib import patheffects
from matplotlib.colors import BoundaryNorm, ListedColormap

sys.path.insert(0, str(Path(__file__).resolve().parent))
import story_figures as SF  # noqa: E402
from story_figures import (BLUES, COL, INK, INK2, LS, RAIN_CMAP, RAIN_NORM, RULE, plt,  # noqa: E402
                           post_hoc_label, post_hoc_runs, say)

EV = "E2_mumbai2005"
REGION = dict(lon=(72.55, 73.35), lat=(18.75, 19.45))    # the area of Litta Fig. 1, a little larger
LABEL_OFFSET = {"Santacruz": (-22, -3), "Colaba": (6, -3), "Vihar Lake": (-26, -2), "Tulsi Lake": (-20, 4),
                "Bhandup": (5, -8), "Thane": (5, 2), "Bhiwandi": (-6, 6), "Kalyan": (5, 2), "Dharavi": (6, -3),
                "Malabar Hill": (-18, -3)}                 # points, so the gauge values do not overlap
T0, T1 = datetime(2005, 7, 26, 3), datetime(2005, 7, 27, 3)
STREAM_TIMES = [datetime(2005, 7, 26, h) for h in (6, 9, 12, 15)]
COLUMN_TIMES = [datetime(2005, 7, 26) + timedelta(hours=h) for h in range(31)]
HEAVY = (datetime(2005, 7, 26, 9), datetime(2005, 7, 26, 21))   # >90% of the Santacruz rain (Litta)
VORT_SMOOTH = 9            # 3 km points: vorticity averaged over 27 km, about the ERA5 grid
COLUMN_HALF = 2            # 3 km points: column means over 5 x 5 points (15 km) around Santacruz
PLEVS = np.arange(1000.0, 149.0, -25.0) * 100.0      # Pa
# relative vorticity, 1e-5 s-1: diverging, blue anticyclonic / red cyclonic, grey near zero
VORT_LEVELS = [-30, -15, -8, -4, 4, 8, 15, 30]
VORT_CMAP = ListedColormap(["#184f95", "#2a78d6", "#6da7ec", "#b7d3f6", "#f0efec",
                            "#f6c4c0", "#ee8a85", "#e34948", "#a82b2a"][1:-1])
VORT_CMAP.set_under("#184f95")
VORT_CMAP.set_over("#a82b2a")
VORT_NORM = BoundaryNorm(VORT_LEVELS, VORT_CMAP.N)
RH_LEVELS = [40, 50, 60, 70, 80, 90, 95, 100]
RH_CMAP = ListedColormap(BLUES[0:13:2])              # 7 steps for the 7 intervals
RH_CMAP.set_under("#ffffff")
RH_CMAP.set_over(BLUES[12])
RH_NORM = BoundaryNorm(RH_LEVELS, RH_CMAP.N)


# ------------------------------------------------------------------------------ helpers ----
def wrf_runs(cfg, runs, driver, dom="d02"):
    """[(label, run directory, colour, line style)]: the WRF run of `driver` and its post-hoc runs."""
    ev = cfg["events"][EV]
    res = "3 km" if dom == "d02" else "12 km"
    ls = LS["3km" if dom == "d02" else "12km"]
    out = [(f"WRF {res}, start {datetime.fromisoformat(ev['sim_start']):%d %b}",
            runs / "wrf" / f"{EV}_{driver}", COL["WRF"], ls)]
    out += [(post_hoc_label(p, res), runs / "wrf" / n, COL["POSTHOC"], ls) for n, p in post_hoc_runs(cfg, EV, driver)]
    return [r for r in out if any(r[1].glob(f"wrfout_{dom}_*"))]


def acc_or_none(d, dom, times):
    """SF.wrf_acc, or None (with a message) for a run that has not reached these times yet."""
    try:
        return SF.wrf_acc(d, dom, times)
    except ValueError as e:
        say(f"  {d.name}: {e}; left out")
        return None


def wrf_at(d, dom, t, names):
    """Values of `names` at time t from the wrfout file that holds it (2-D/3-D arrays, Time dropped)."""
    for f in sorted(d.glob(f"wrfout_{dom}_*")):
        ts = SF.wrf_times(f)
        if t in ts:
            with xr.open_dataset(f, decode_times=False) as ds:
                missing = [v for v in names if v not in ds]
                if missing:
                    raise KeyError(f"{f.name} lacks {missing} (slim archive?)")
                out = {v: ds[v].isel(Time=ts.index(t)).values for v in names}   # one time only
                out["DX"] = float(ds.attrs["DX"])
                out["TRUELAT1"] = float(ds.attrs.get("TRUELAT1", 0.0))
            return out
    raise KeyError(f"{d.name}/{dom}: no output at {t}")


def destagger(a, axis):
    sl0 = [slice(None)] * a.ndim
    sl1 = [slice(None)] * a.ndim
    sl0[axis], sl1[axis] = slice(0, -1), slice(1, None)
    return 0.5 * (a[tuple(sl0)] + a[tuple(sl1)])


def to_plev(f, p, plevs):
    """Interpolate f (nz, ...) on pressure p (nz, ..., decreasing upwards) to plevs, linear in ln p;
    NaN outside the column."""
    lp, out = np.log(p), np.full((len(plevs),) + f.shape[1:], np.nan)
    for i, pl in enumerate(plevs):
        k = np.argmax(p < pl, axis=0)                       # first level above pl
        ok = (k > 0) & (p[0] >= pl)
        k = np.clip(k, 1, p.shape[0] - 1)
        lo = np.take_along_axis(lp, k[None] - 1, 0)[0]
        hi = np.take_along_axis(lp, k[None], 0)[0]
        w = (np.log(pl) - lo) / (hi - lo)
        fl = np.take_along_axis(f, k[None] - 1, 0)[0]
        fh = np.take_along_axis(f, k[None], 0)[0]
        out[i] = np.where(ok, fl + w * (fh - fl), np.nan)
    return out


def rh(t_k, q, p):
    """Relative humidity (%) over water from temperature (K), specific humidity or mixing ratio
    (kg/kg, the difference is < 2% here) and pressure (Pa); Bolton (1980) saturation pressure."""
    e = q * p / (0.622 + q)
    es = 611.2 * np.exp(17.67 * (t_k - 273.15) / (t_k - 29.65))
    return 100.0 * e / es


def box_mean(a, n):
    """n x n moving mean over the last two axes (edges: mean of the points available)."""
    from scipy.ndimage import uniform_filter
    return uniform_filter(a, size=(1,) * (a.ndim - 2) + (n, n), mode="nearest")


def regular(lat1d, lon1d, *fields):
    """Fields on a Mercator grid (lat depends on j only, lon on i only) -> evenly spaced lat/lon,
    as streamplot needs."""
    lat1d, lon1d = np.asarray(lat1d, dtype="float64"), np.asarray(lon1d, dtype="float64")
    lat_r = np.linspace(lat1d[0], lat1d[-1], len(lat1d))      # float64: streamplot checks the spacing
    lon_r = np.linspace(lon1d[0], lon1d[-1], len(lon1d))
    out = []
    for f in fields:
        g = np.empty_like(f)
        for i in range(f.shape[1]):
            g[:, i] = np.interp(lat_r, lat1d, f[:, i])
        out.append(g)
    return lat_r, lon_r, out


def wrf_500(d, t):
    """lat, lon (1-D, regular), u, v (m/s) and relative vorticity (1e-5 s-1, 27 km mean) at 500 hPa."""
    x = wrf_at(d, "d02", t, ["U", "V", "P", "PB", "XLAT", "XLONG"])
    p = x["P"] + x["PB"]
    u = to_plev(destagger(x["U"], 2), p, [5.0e4])[0]
    v = to_plev(destagger(x["V"], 1), p, [5.0e4])[0]
    lat, lon = x["XLAT"], x["XLONG"]
    m = np.cos(np.radians(x["TRUELAT1"])) / np.cos(np.radians(lat))     # Mercator map factor
    dx = x["DX"]
    zeta = m ** 2 * (np.gradient(v / m, dx, axis=1) - np.gradient(u / m, dx, axis=0))
    zeta = box_mean(np.nan_to_num(zeta), VORT_SMOOTH) * 1e5
    la, lo, (u, v, zeta) = regular(lat[:, 0], lon[0, :], u, v, zeta)
    return la, lo, u, v, zeta


def driver_500(driver, t, lat_rng, lon_rng):
    f = SF.DATA / "drivers" / f"{EV}_{driver}.nc"
    ds = xr.open_dataset(f).sel(time=np.datetime64(t), plev=5.0e4, method="nearest")
    ds = ds.sel(lat=slice(lat_rng[0] - 0.5, lat_rng[1] + 0.5), lon=slice(lon_rng[0] - 0.5, lon_rng[1] + 0.5))
    lat, lon = ds["lat"].values.astype(float), ds["lon"].values.astype(float)
    u, v = ds["U"].values.astype(float), ds["V"].values.astype(float)
    a = 6.371e6
    phi, lam = np.radians(lat)[:, None], np.radians(lon)
    zeta = (np.gradient(v, lam, axis=1) - np.gradient(u * np.cos(phi), np.radians(lat), axis=0)) / (a * np.cos(phi))
    return (np.linspace(lat[0], lat[-1], len(lat)), np.linspace(lon[0], lon[-1], len(lon)), u, v, zeta * 1e5)


def mark_mumbai(ax, **kw):
    ax.plot(SF.SANTACRUZ[1], SF.SANTACRUZ[0], marker="*", ms=7, color=INK, mec="white", mew=0.5, zorder=6, **kw)


# --------------------------------------------------------------------------- fig 8 ----
def fig_stations(cfg, runs, out):
    st = SF.load_stations()
    if st is None:
        return say("fig8: no config/stations_mumbai2005.yaml, skipped")
    ev = cfg["events"][EV]
    panels = []
    imd = xr.open_dataset(SF.DATA / "obs" / "imd_rain_2005.nc")["rain"]
    lab = T1.date() if cfg["observations"]["imd_label"] == "backward" else T0.date()
    io = imd.sel(time=np.datetime64(lab)).sel(lat=slice(18.0, 20.25), lon=slice(72.0, 74.0))
    lo2, la2 = np.meshgrid(io["lon"].values, io["lat"].values)
    panels.append(("IMD 0.25° grid (observed)", la2, lo2, io.values))
    for drv in ev["drivers"]:
        for name, d, _, _ in wrf_runs(cfg, runs, drv):
            w = acc_or_none(d, "d02", [T0, T1])
            if w is not None:
                acc, fl = w
                panels.append((f"{name}, {drv}", fl["lat"], fl["lon"], acc[T1] - acc[T0]))
        r = SF.regcm_total(runs / "regcm" / f"{EV}_{drv}_03km", T0, T1)
        if r is not None:
            panels.append((f"RegCM5 3 km, {drv}", r[1], r[2], r[0]))
    if len(panels) == 1:
        return say("fig8: no 3 km output, skipped")
    nc = 3
    nr = int(np.ceil(len(panels) / nc))
    fig, axes = plt.subplots(nr, nc, figsize=(3.0 * nc, 2.45 * nr + 0.6), squeeze=False, sharex=True, sharey=True)
    names = list(st["stations"])
    sla = np.array([st["stations"][n][0] for n in names])
    slo = np.array([st["stations"][n][1] for n in names])
    sv = np.array([st["stations"][n][2] for n in names])
    for k, ax in enumerate(axes.flat):
        if k >= len(panels):
            ax.axis("off")
            continue
        title, la, lo, f = panels[k]
        pc = ax.pcolormesh(lo, la, f, cmap=RAIN_CMAP, norm=RAIN_NORM, shading="nearest")
        ax.set_xlim(*REGION["lon"])
        ax.set_ylim(*REGION["lat"])
        ax.set_aspect("equal")
        SF.borders(ax, lw=0.6, states=True)
        ax.scatter(slo, sla, c=sv, cmap=RAIN_CMAP, norm=RAIN_NORM, s=34, edgecolors=INK, linewidths=0.8, zorder=7)
        inr = (la >= REGION["lat"][0]) & (la <= REGION["lat"][1]) & (lo >= REGION["lon"][0]) & (lo <= REGION["lon"][1])
        j = SF.nearest(np.where(np.isfinite(f), la, 1.0e3), lo, SF.SANTACRUZ)   # nearest cell with data
        fmax = np.nanmax(np.where(inr, f, np.nan))
        ax.text(0.97, 0.03, f"cell nearest Santacruz {f[j]:.0f} mm\nmax in map {fmax:.0f} mm", transform=ax.transAxes,
                fontsize=6.5, va="bottom", ha="right", color=INK, zorder=9,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=RULE, lw=0.5))
        ax.set_title(title, fontsize=7.5)
        if k == 0:
            for n, a, o, v in zip(names, sla, slo, sv):
                dx, dy = LABEL_OFFSET.get(n, (5, 2))
                ax.annotate(f"{v:.0f}", (o, a), xytext=(dx, dy), textcoords="offset points", fontsize=6, color=INK,
                            zorder=8, path_effects=[patheffects.withStroke(linewidth=2, foreground="white")])
    for ax in axes[-1]:
        ax.set_xlabel("longitude (°E)")
    for ax in axes[:, 0]:
        ax.set_ylabel("latitude (°N)")
    SF.rain_colorbar(fig, pc, axes, "rain, 24 h to 08:30 IST 27 July 2005 (mm)")
    fig.suptitle("Mumbai, 26 July 2005: 24 h rain to 08:30 IST 27 July. Dots: rain gauges (IMD, via Litta et al. "
                 "2007, Fig. 1),\ncoloured on the same scale; gauge values (mm) in the first panel.",
                 fontsize=8)
    fig.savefig(out / "fig8_E2_stations.png", bbox_inches="tight")
    plt.close(fig)
    say("fig8 written")


# --------------------------------------------------------------------------- fig 9 ----
def series_at(d, dom, p, times):
    w = acc_or_none(d, dom, times)
    if w is None:
        return None
    acc, fl = w
    j = SF.nearest(fl["lat"], fl["lon"], p)
    return np.array([acc[t][j] - acc[times[0]][j] for t in times])


def regcm_series_at(d, p, times):
    r = SF.regcm_pr(d)
    if r is None:
        return None
    pr, la, lo = r
    j = SF.nearest(la, lo, p)
    t = pr["time"].values.astype("datetime64[s]")
    hourly = pr.values[:, j[0], j[1]] * 3600.0
    return np.array([hourly[(t > np.datetime64(times[0], "s")) & (t <= np.datetime64(x, "s"))].sum() for x in times])


def fig_3hourly(cfg, runs, out):
    st = SF.load_stations()
    if st is None:
        return say("fig9: no config/stations_mumbai2005.yaml, skipped")
    th = st["three_hourly"]
    times = th["times"]
    xh = [(t - times[0]).total_seconds() / 3600.0 for t in times]
    drvs = cfg["events"][EV]["drivers"]
    places = [("Santacruz", st["stations"]["Santacruz"]), ("Colaba", st["stations"]["Colaba"])]
    fig, axes = plt.subplots(len(drvs), 2, figsize=(9.0, 3.3 * len(drvs) + 0.5), squeeze=False, sharex=True)
    drawn = False
    for i, drv in enumerate(drvs):
        for j, (pname, (la, lo, tot, _)) in enumerate(places):
            ax = axes[i, j]
            p = (la, lo)
            ax.plot(xh, [10.0 * v for v in th[f"{pname}_cm"]], color=COL["IMD"], lw=2.4, marker="o", ms=4, zorder=6,
                    label="observed (IMD gauge)")
            for dom in ("d01", "d02"):
                for name, d, colr, ls in wrf_runs(cfg, runs, drv, dom):
                    s = series_at(d, dom, p, times)
                    if s is not None:
                        ax.plot(xh, s, color=colr, ls=ls, lw=1.6, marker="o" if dom == "d02" else None, ms=3,
                                label=name)
                        drawn = True
            for res in ("12km", "03km"):
                s = regcm_series_at(runs / "regcm" / f"{EV}_{drv}_{res}", p, times)
                if s is not None:
                    run = f"RegCM_{res.lstrip('0')}_{drv}"
                    ax.plot(xh, s, label=SF.label(run).replace("RegCM", "RegCM5"), **SF.style(run))
            ax.set_title(f"{pname} (observed {tot:.0f} mm), driven by {drv}", loc="left", fontsize=8)
            ax.grid(axis="y", color=RULE, lw=0.5)
            ax.spines[["top", "right"]].set_visible(False)
            ax.set_ylim(bottom=0)
            if j == 0:
                ax.set_ylabel("rain since 06 UTC 26 July (mm)")
        axes[i, -1].legend(fontsize=6.5, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    if not drawn:
        plt.close(fig)
        return say("fig9: no E2 WRF output, skipped")
    for ax in axes[-1]:
        ax.set_xticks(xh, [f"{t:%H}Z" for t in times])
        ax.set_xlabel("UTC, 26-27 July 2005 (IST = UTC + 5:30)")
    fig.suptitle("Rain every 3 h at Santacruz and Colaba (25 km apart), as in Litta et al. (2007, Fig. 2): "
                 "gauges and the nearest model grid point", fontsize=8.5)
    fig.savefig(out / "fig9_E2_3hourly.png", bbox_inches="tight")
    plt.close(fig)
    say("fig9 written")


# -------------------------------------------------------------------------- fig 10 ----
def fig_500(cfg, runs, out):
    rows = wrf_runs(cfg, runs, "ERA5")
    if not rows:
        return say("fig10: no ERA5-driven WRF output, skipped")
    try:
        first = wrf_500(rows[0][1], STREAM_TIMES[0])
    except KeyError as e:
        return say(f"fig10: {e}; skipped")
    lat_rng, lon_rng = (first[0].min(), first[0].max()), (first[1].min(), first[1].max())
    labels = [(f"ERA5 (0.25°)", None)] + [(name + ", ERA5", d) for name, d, _, _ in rows]
    fig, axes = plt.subplots(len(labels), len(STREAM_TIMES), figsize=(2.55 * len(STREAM_TIMES), 1.95 * len(labels) + 0.9),
                             squeeze=False, sharex=True, sharey=True)
    pc = None
    for i, (name, d) in enumerate(labels):
        for j, t in enumerate(STREAM_TIMES):
            ax = axes[i, j]
            try:
                la, lo, u, v, z = driver_500("ERA5", t, lat_rng, lon_rng) if d is None else wrf_500(d, t)
            except (KeyError, FileNotFoundError, OSError) as e:
                ax.axis("off")
                say(f"fig10 {name} {t:%H} UTC: {e}")
                continue
            pc = ax.pcolormesh(lo, la, z, cmap=VORT_CMAP, norm=VORT_NORM, shading="nearest")
            ax.streamplot(lo, la, u, v, color=INK, linewidth=0.5, density=1.1, arrowsize=0.6)
            ax.set_xlim(*lon_rng)
            ax.set_ylim(*lat_rng)
            ax.set_aspect("equal")
            SF.borders(ax, lw=0.45, states=False)
            mark_mumbai(ax)
            if i == 0:
                ax.set_title(f"{t:%H} UTC ({t + timedelta(hours=5, minutes=30):%H:%M} IST)", fontsize=8)
            if j == 0:
                ax.set_ylabel(f"{name}\nlatitude (°N)", fontsize=7)
    for ax in axes[-1]:
        ax.set_xlabel("longitude (°E)")
    if pc is not None:
        cb = fig.colorbar(pc, ax=axes, shrink=0.6, pad=0.02, extend="both")
        cb.set_label("relative vorticity at 500 hPa (10⁻⁵ s⁻¹)")
        cb.outline.set_edgecolor(RULE)
    fig.suptitle("500 hPa streamlines and relative vorticity, 26 July 2005 (as Litta et al. 2007, Fig. 7). "
                 "WRF vorticity is averaged over 27 km,\nabout the ERA5 grid; red: cyclonic. Star: Santacruz.",
                 fontsize=8)
    fig.savefig(out / "fig10_E2_500hPa.png", bbox_inches="tight")
    plt.close(fig)
    say("fig10 written")


# -------------------------------------------------------------------------- fig 11 ----
def wrf_column(d, times):
    """RH (%), w (m/s), u, v (m/s) on PLEVS x times, means over the 15 km box around Santacruz."""
    ji = None
    out = {k: np.full((len(PLEVS), len(times)), np.nan) for k in ("rh", "w", "u", "v")}
    for n, t in enumerate(times):
        x = wrf_at(d, "d02", t, ["U", "V", "W", "T", "P", "PB", "QVAPOR", "XLAT", "XLONG"])
        if ji is None:
            j, i = SF.nearest(x["XLAT"], x["XLONG"], SF.SANTACRUZ)
            ji = (slice(j - COLUMN_HALF, j + COLUMN_HALF + 1), slice(i - COLUMN_HALF, i + COLUMN_HALF + 1))
        p = (x["P"] + x["PB"])[:, ji[0], ji[1]]
        tk = (x["T"][:, ji[0], ji[1]] + 300.0) * (p / 1.0e5) ** (287.04 / 1004.5)
        f = dict(rh=rh(tk, x["QVAPOR"][:, ji[0], ji[1]], p),
                 w=destagger(x["W"], 0)[:, ji[0], ji[1]],
                 u=destagger(x["U"], 2)[:, ji[0], ji[1]], v=destagger(x["V"], 1)[:, ji[0], ji[1]])
        with warnings.catch_warnings():              # levels below ground: all-NaN, kept as NaN
            warnings.simplefilter("ignore", RuntimeWarning)
            for k, a in f.items():
                out[k][:, n] = np.nanmean(to_plev(a, p, PLEVS), axis=(1, 2))
    return out


def driver_column(driver, times):
    f = SF.DATA / "drivers" / f"{EV}_{driver}.nc"
    ds = xr.open_dataset(f).sel(lat=SF.SANTACRUZ[0], lon=SF.SANTACRUZ[1], method="nearest")
    tt = [t for t in times if np.datetime64(t) in ds["time"].values.astype("datetime64[ns]")]
    ds = ds.sel(time=[np.datetime64(t) for t in tt])
    p = ds["plev"].values.astype(float)
    ok = p >= PLEVS.min() - 1
    ps = ds["PSFC"].values[:, None]
    above = p[None, ok] <= ps
    r = np.where(above, rh(ds["T"].values[:, ok], ds["Q"].values[:, ok], p[None, ok]), np.nan)
    return tt, p[ok], dict(rh=r.T, u=np.where(above, ds["U"].values[:, ok], np.nan).T,
                           v=np.where(above, ds["V"].values[:, ok], np.nan).T)


def fig_column(cfg, runs, out):
    rows = wrf_runs(cfg, runs, "ERA5")
    panels = []
    for name, d, _, _ in rows:
        try:
            panels.append((f"{name}, ERA5 (mean over 15 km)", COLUMN_TIMES, PLEVS, wrf_column(d, COLUMN_TIMES)))
        except KeyError as e:
            say(f"fig11 {name}: {e}")
    f = SF.DATA / "drivers" / f"{EV}_ERA5.nc"
    if f.exists():
        tt, p, c = driver_column("ERA5", COLUMN_TIMES)
        panels.insert(0, ("ERA5 (0.25° grid point)", tt, p, c))
    if not panels or all("w" not in c for _, _, _, c in panels):
        return say("fig11: no model columns (full wrfout files needed), skipped")
    fig, axes = plt.subplots(len(panels), 1, figsize=(8.0, 2.6 * len(panels) + 0.6), squeeze=False, sharex=True)
    t0 = COLUMN_TIMES[0]
    hrs = lambda ts: np.array([(t - t0).total_seconds() / 3600.0 for t in ts])
    pc = None
    for ax, (name, ts, p, c) in zip(axes[:, 0], panels):
        x = hrs(ts)
        pc = ax.contourf(x, p / 100.0, c["rh"], levels=RH_LEVELS, cmap=RH_CMAP, norm=RH_NORM, extend="both")
        if "w" in c:
            lv = [0.05, 0.1, 0.2, 0.5, 1.0]
            cs = ax.contour(x, p / 100.0, c["w"], levels=lv, colors=INK, linewidths=0.7)
            ax.clabel(cs, fmt="%g", fontsize=5.5)
            ax.contour(x, p / 100.0, c["w"], levels=[-v for v in lv[::-1]], colors=INK2, linewidths=0.6,
                       linestyles="--")
        kp = [k for k, v in enumerate(p) if round(v / 100) in (950, 850, 700, 600, 500, 400, 300, 200)]
        kt = [k for k, t in enumerate(ts) if t.hour % 3 == 0]
        X, Y = np.meshgrid(x[kt], p[kp] / 100.0)
        ax.barbs(X, Y, c["u"][np.ix_(kp, kt)] * 1.944, c["v"][np.ix_(kp, kt)] * 1.944, length=4.5, linewidth=0.4,
                 color=INK)
        for h in HEAVY:
            ax.axvline((h - t0).total_seconds() / 3600.0, color="#e34948", lw=0.9, ls=(0, (3, 2)))
        ax.set_ylim(1000, 150)
        ax.set_yticks([1000, 850, 700, 500, 300, 200])
        ax.set_ylabel("pressure (hPa)")
        ax.set_title(name, loc="left", fontsize=8)
    axes[-1, 0].set_xticks(range(0, 31, 3), [f"{(t0 + timedelta(hours=h)):%d/%H}Z" for h in range(0, 31, 3)])
    axes[-1, 0].set_xlabel("day/hour UTC, July 2005")
    cb = fig.colorbar(pc, ax=axes[:, 0], shrink=0.7, pad=0.02, extend="both")
    cb.set_label("relative humidity (%)")
    cb.outline.set_edgecolor(RULE)
    fig.suptitle("Above Santacruz, 26-27 July 2005: relative humidity (shading), vertical velocity (m/s; solid up, "
                 "dashed down)\nand wind (barbs, knots). Red dashed lines: 09-21 UTC, when over 90% of the "
                 "944 mm fell (Litta et al. 2007).", fontsize=8)
    fig.savefig(out / "fig11_E2_column.png", bbox_inches="tight")
    plt.close(fig)
    say("fig11 written")


def make_all(cfg, runs, out):
    if EV not in cfg["events"]:
        return
    for name, fn in (("fig8", fig_stations), ("fig9", fig_3hourly), ("fig10", fig_500), ("fig11", fig_column)):
        try:
            fn(cfg, runs, out)
        except Exception as e:                       # one broken figure must not stop the others
            say(f"{name} FAILED: {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", type=Path, required=True)
    a = ap.parse_args()
    out = SF.ROOT / "results" / "figures" / "story"
    out.mkdir(parents=True, exist_ok=True)
    make_all(SF.load_config(), a.runs_root, out)


if __name__ == "__main__":
    main()
