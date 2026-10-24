"""Coastlines, the boundary of India and its state boundaries on a matplotlib map (lon/lat axes).

    from boundaries import draw_boundaries
    draw_boundaries(ax)               # after setting the axes limits

Lines come from assets/boundaries/*.geojson (sources and licences in its README.md):
India's coast and land boundary and the state boundaries as depicted by the Government of
India (DataMeet), other countries from Natural Earth (India point of view). Needs only json
and matplotlib.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from matplotlib.collections import LineCollection

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "boundaries"
INK, INK2 = "#0b0b0b", "#52514e"
CREDIT = "Boundaries: DataMeet (India, states), Natural Earth (other countries)"


@lru_cache(maxsize=None)
def _lines(name: str) -> tuple:
    f = ASSETS / f"{name}.geojson"
    if not f.exists():
        return ()
    fc = json.loads(f.read_text())
    return tuple(np.asarray(ft["geometry"]["coordinates"], dtype=float) for ft in fc["features"])


def available() -> bool:
    return all((ASSETS / f"{n}.geojson").exists() for n in ("india_outline", "india_states", "neighbours"))


def draw_boundaries(ax, states: bool = True, lw: float = 0.6, color: str = INK, state_color: str = INK2,
                    zorder: float = 4):
    """Draw the lines that fall inside the current axes limits; the limits are kept.
    Returns False when the boundary files are missing (nothing drawn)."""
    if not available():
        return False
    x0, x1 = sorted(ax.get_xlim())
    y0, y1 = sorted(ax.get_ylim())
    pad = 0.5

    def keep(segs):
        return [s for s in segs if s[:, 0].max() >= x0 - pad and s[:, 0].min() <= x1 + pad
                and s[:, 1].max() >= y0 - pad and s[:, 1].min() <= y1 + pad]

    xl, yl = ax.get_xlim(), ax.get_ylim()
    if states:
        ax.add_collection(LineCollection(keep(_lines("india_states")), colors=state_color, linewidths=0.55 * lw,
                                         linestyles=(0, (4, 1.5)), zorder=zorder))
    ax.add_collection(LineCollection(keep(_lines("neighbours")), colors=color, linewidths=lw, zorder=zorder))
    ax.add_collection(LineCollection(keep(_lines("india_outline")), colors=color, linewidths=lw, zorder=zorder))
    ax.set_xlim(xl)
    ax.set_ylim(yl)
    return True
