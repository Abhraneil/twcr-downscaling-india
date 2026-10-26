#!/usr/bin/env python3
"""Choose the 20 events of the multi-event study objectively from the IMD gridded rainfall.

    python scripts/download/get_imd.py $(seq 1901 2015)         # data/obs/imd_rain_<year>.nc
    python scripts/events/select_events.py                      # results/multievent/

The rule (docs/multievent/design.md, fixed before the ranking was first run):
  1. Severity of a day: the rain of three consecutive IMD days, averaged over a 5 x 5-cell box
     (1.25 deg, about 130 km side) around each cell, using the box's cells that have data on all
     three days; at least 13 of the 25 cells must have data (so coastal boxes count).
  2. Region of a box: by its centre (region() below). Era: 1901-1939 (20CRv3 only) or
     1940-2015 (ERA5 exists too), by the first day of the window.
  3. Independent events: in each year and region the largest box-window is taken, then everything
     within 7 days and 500 km of it is removed, and so on (CANDIDATES_PER_YEAR per region and year).
     Across regions, a candidate within 7 days and 500 km of a larger one already chosen is the same
     storm and is dropped.
  4. The two largest independent events in each region and era: 5 regions x 2 eras x 2 = 20.
  5. Each event's simulation and scoring dates follow from its IMD days (design.md); the last
     usable window ends on 27 December 2015 so that its simulation ends inside 20CRv3.
Also reported, not used for the choice: the box value relative to the box's mean annual maximum
(how unusual the event was locally) and the share of the box total from its wettest cell (a
total carried by one cell is checked against documents before the event is accepted; design.md).

Writes results/multievent/candidates.csv (the ten largest independent events per region and era,
with ranks), selected.csv, SELECTED.md and map_selected.png.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from scipy.ndimage import uniform_filter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA, ROOT  # noqa: E402

DAYS = 3                    # IMD days per window
BOX = 5                     # cells per box side (0.25 deg cells)
MIN_VALID = 13              # cells with data out of BOX*BOX
SEP_DAYS, SEP_KM = 7, 500.0
CANDIDATES_PER_YEAR = 5     # per region, after declustering within the year
PER_STRATUM = 2
ERAS = [("1901-1939", 1901, 1939), ("1940-2015", 1940, 2015)]
LAST_LABEL = date(2015, 12, 27)
# Indian west coast, (lat, lon) of coastal towns from Thiruvananthapuram to Valsad; the
# "West coast and Ghats" band reaches GHATS_BAND inland from it: the Ghats crest is 0.4-0.8 deg
# inland (Agumbe, Mahabaleshwar, Munnar), the rain-shadow towns behind it (Pune) are further east.
WEST_COAST = [(8.5, 76.95), (10.0, 76.25), (11.25, 75.8), (12.9, 74.85), (14.8, 74.15), (15.5, 73.8),
              (17.0, 73.3), (19.0, 72.85), (20.0, 72.75), (21.5, 72.75)]
GHATS_BAND = 0.85            # deg of longitude
REGIONS = ["West coast and Ghats", "Central and south", "North and northwest", "East", "Northeast"]


def region(lat: float, lon: float) -> str:
    """Region of a box centre. Checked in this order; the rules are in docs/multievent/design.md."""
    if lon >= 89.5:
        return "Northeast"
    if lat >= 23.5 and lon < 82.0:
        return "North and northwest"
    if lat >= 18.0 and lon >= 82.0:
        return "East"
    if lat < 21.5 and lon < np.interp(lat, *zip(*WEST_COAST)) + GHATS_BAND:
        return "West coast and Ghats"
    return "Central and south"


def km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def load_year(y: int, obs: Path) -> xr.DataArray | None:
    f = obs / f"imd_rain_{y}.nc"
    return xr.open_dataset(f)["rain"].load() if f.exists() else None


def windows(rain: np.ndarray):
    """3-day sums (n-DAYS+1, ny, nx) and box means over cells with data on all three days."""
    ok = np.isfinite(rain)
    r = np.where(ok, rain, 0.0)
    s3 = sum(r[k:len(r) - DAYS + 1 + k] for k in range(DAYS))
    v3 = np.all([ok[k:len(ok) - DAYS + 1 + k] for k in range(DAYS)], axis=0)
    n = BOX * BOX
    cnt = uniform_filter(v3.astype("float64"), size=(1, BOX, BOX), mode="constant") * n
    tot = uniform_filter(np.where(v3, s3, 0.0), size=(1, BOX, BOX), mode="constant") * n
    with np.errstate(invalid="ignore", divide="ignore"):
        box = np.where(cnt >= MIN_VALID - 0.5, tot / cnt, np.nan)
    return s3, v3, box, np.rint(cnt).astype(int)


def candidates_for_year(y, rain, labels, lat, lon, reg_idx):
    """Independent box-windows of one year, the largest CANDIDATES_PER_YEAR in each region."""
    s3, v3, box, cnt = windows(rain)
    la2, lo2 = np.meshgrid(lat, lon, indexing="ij")
    out = []
    annual_max = np.nanmax(np.where(np.isfinite(box), box, -np.inf), axis=0)
    for r, name in enumerate(REGIONS):
        b = np.where(reg_idx[None] == r, box, np.nan)
        found = 0
        while found < CANDIDATES_PER_YEAR and np.isfinite(b).any():
            t, i, j = np.unravel_index(np.nanargmax(b), b.shape)
            first = labels[t]
            if first.year != y:                       # window starts in the next year's days
                b[t] = np.nan
                continue
            found += 1
            sl = (slice(max(i - BOX // 2, 0), i + BOX // 2 + 1), slice(max(j - BOX // 2, 0), j + BOX // 2 + 1))
            cells = np.where(v3[t][sl], s3[t][sl], np.nan)
            out.append(dict(region=name, first_label=first, last_label=labels[t + DAYS - 1],
                            lat=float(lat[i]), lon=float(lon[j]), box_mm=float(box[t, i, j]),
                            peak_cell_3day_mm=float(np.nanmax(cells)),
                            peak_cell_day_mm=float(np.nanmax(rain[t:t + DAYS][(slice(None),) + sl])),
                            wettest_cell_share=float(np.nanmax(cells) / np.nansum(cells)),
                            cells_with_data=int(cnt[t, i, j])))
            near = km(lat[i], lon[j], la2, lo2) <= SEP_KM
            b[max(t - SEP_DAYS, 0):t + SEP_DAYS + 1, near] = np.nan
    return out, annual_max


def select(cands: pd.DataFrame) -> pd.DataFrame:
    """Steps 3-4: decluster across regions (largest first), then the top PER_STRATUM per stratum."""
    cands = cands.sort_values("box_mm", ascending=False).reset_index(drop=True)
    kept = []
    for c in cands.itertuples():
        same = any(abs((c.first_label - k.first_label).days) <= SEP_DAYS and
                   km(c.lat, c.lon, k.lat, k.lon) <= SEP_KM for k in kept)
        if not same:
            kept.append(c)
    ind = pd.DataFrame([k._asdict() for k in kept]).drop(columns="Index")
    ind["rank_in_stratum"] = ind.groupby(["era", "region"])["box_mm"].rank(ascending=False, method="first").astype(int)
    return ind.sort_values(["era", "region", "rank_in_stratum"]).reset_index(drop=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=int, default=1901)
    ap.add_argument("--last", type=int, default=2015)
    ap.add_argument("--obs", type=Path, default=DATA / "obs")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "multievent")
    ap.add_argument("--eras", default=None, help="for tests: 'name:first:last,...'")
    a = ap.parse_args(argv)
    eras = ERAS if a.eras is None else [(n, int(f), int(l)) for n, f, l in (e.split(":") for e in a.eras.split(","))]
    missing = [y for y in range(a.first, a.last + 1) if not (a.obs / f"imd_rain_{y}.nc").exists()]
    if missing:
        sys.exit(f"missing IMD years {missing[:5]}{'...' if len(missing) > 5 else ''}: run scripts/download/get_imd.py")
    rows, amax, reg_idx = [], [], None
    nxt = load_year(a.first, a.obs)
    for y in range(a.first, a.last + 1):
        cur, nxt = nxt, (load_year(y + 1, a.obs) if y < a.last else None)
        rain = cur.values.astype("float64")
        labels = [pd.Timestamp(t).date() for t in cur["time"].values]
        if nxt is not None:                           # windows that start on 30/31 December
            rain = np.concatenate([rain, nxt.values[:DAYS - 1].astype("float64")])
            labels += [pd.Timestamp(t).date() for t in nxt["time"].values[:DAYS - 1]]
        lat, lon = cur["lat"].values, cur["lon"].values
        if reg_idx is None:
            reg_idx = np.array([[REGIONS.index(region(p, q)) for q in lon] for p in lat])
        c, am = candidates_for_year(y, rain, labels, lat, lon, reg_idx)
        rows += [r for r in c if r["last_label"] <= LAST_LABEL]
        amax.append(am)
        print(f"{y}: {len(c)} candidates", flush=True)
    cands = pd.DataFrame(rows)
    cands["era"] = [next((n for n, f, l in eras if f <= d.year <= l), None) for d in cands.first_label]
    cands = cands[cands.era.notna()]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)     # boxes never valid stay NaN
        mean_am = np.nanmean(np.where(np.isfinite(np.array(amax)), np.array(amax), np.nan), axis=0)
    ii = [int(np.argmin(abs(lat - p))) for p in cands.lat]
    jj = [int(np.argmin(abs(lon - q))) for q in cands.lon]
    cands["box_over_mean_annual_max"] = cands.box_mm.values / mean_am[ii, jj]
    ind = select(cands)
    a.out.mkdir(parents=True, exist_ok=True)
    top = ind[ind.rank_in_stratum <= 10]
    top.to_csv(a.out / "candidates.csv", index=False, float_format="%.2f")
    sel = ind[ind.rank_in_stratum <= PER_STRATUM].copy()
    sel.insert(0, "event", [f"M{k + 1:02d}" for k in range(len(sel))])
    sel.to_csv(a.out / "selected.csv", index=False, float_format="%.2f")
    cols = ["event", "era", "region", "first_label", "last_label", "lat", "lon", "box_mm", "peak_cell_3day_mm",
            "peak_cell_day_mm", "box_over_mean_annual_max", "wettest_cell_share"]
    md = ["# Events selected by scripts/events/select_events.py", "",
          f"IMD 0.25 deg, {a.first}-{a.last}; {DAYS}-day rain averaged over {BOX}x{BOX}-cell boxes; independent "
          f"events ({SEP_DAYS} days / {SEP_KM:.0f} km); the {PER_STRATUM} largest per region and era. "
          "`first_label`/`last_label` are IMD date labels; mm are 3-day totals. "
          "`wettest_cell_share` above 0.5 means one cell carries over half the box total (checked against "
          "documents, design.md). The documentary record of each event is in docs/multievent/events.md.", "",
          sel[cols].to_markdown(index=False, floatfmt=".2f"), ""]
    (a.out / "SELECTED.md").write_text("\n".join(md))
    print("\n".join(md))
    try:
        plot(sel, a.out / "map_selected.png")
    except Exception as e:                            # the tables are the result; the map is a view of them
        print(f"map not drawn: {type(e).__name__}: {e}")


def plot(sel, f):
    sys.path.insert(0, str(ROOT / "scripts" / "scoring"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from boundaries import draw_boundaries
    fig, ax = plt.subplots(figsize=(6.4, 6.6))
    ax.set_xlim(66, 98.5)
    ax.set_ylim(6, 37.5)
    ax.set_aspect("equal")
    draw_boundaries(ax, lw=0.5)
    for era, mk, col in (("1901-1939", "s", "#eb6834"), ("1940-2015", "o", "#2a78d6")):
        s = sel[sel.era == era]
        ax.scatter(s.lon, s.lat, s=20 + s.box_mm / 4, marker=mk, color=col, edgecolors="#0b0b0b", linewidths=0.6,
                   zorder=6, label=f"{era} ({len(s)})")
        for e in s.itertuples():
            ax.annotate(f"{e.event} {e.first_label:%Y}", (e.lon, e.lat), xytext=(5, 3), textcoords="offset points",
                        fontsize=6.5, zorder=7)
    ax.legend(loc="lower left", fontsize=7, title="first day of the window", title_fontsize=7)
    ax.set_xlabel("longitude (°E)")
    ax.set_ylabel("latitude (°N)")
    ax.set_title("Selected events (marker size: 3-day box-mean rain)", fontsize=9)
    fig.savefig(f, dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
