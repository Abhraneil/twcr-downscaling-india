"""Verification metrics for daily precipitation fields on a common lat-lon grid.

All functions take model and observation arrays of identical shape and a boolean
`mask` of cells to use (IMD-valid land cells inside the scoring box). NaN in the
model inside the mask is an error, not something to skip.

References
  Roberts & Lean 2008, MWR 136:78-97              (fractions skill score)
  Wernli et al. 2008, MWR 136:4470-4487           (SAL)
  Wernli et al. 2009, Wea. Forecasting 24:1472    (SAL threshold R* = R95 / 15)
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

R_KM = 6371.0


def _check(m, o, mask):
    if m.shape != o.shape or m.shape[-2:] != mask.shape:
        raise ValueError("shape mismatch")
    if np.isnan(m[..., mask]).any():
        raise ValueError("model has NaN inside the scoring mask (domain or remap problem)")
    if np.isnan(o[..., mask]).any():
        raise ValueError("observations have NaN inside the scoring mask")


def area_weights(lat, lon):
    w = np.cos(np.radians(lat))[:, None] * np.ones(len(lon))[None, :]
    return w


def area_mean(a, mask, w):
    """Area-weighted mean over the mask; for (day, y, x) input also averaged over days."""
    v = np.sum(a[..., mask] * w[mask], axis=-1) / np.sum(w[mask])
    return float(np.mean(v))


def bias_pct(m, o, mask, w):
    """Relative bias of the area-weighted mean (%)."""
    _check(m, o, mask)
    om = area_mean(o, mask, w)
    return 100.0 * (area_mean(m, mask, w) - om) / om


def pattern_corr(m2, o2, mask, w):
    """Area-weighted centred pattern correlation of 2-D fields."""
    _check(m2, o2, mask)
    a, b, ww = m2[mask], o2[mask], w[mask]
    a = a - np.sum(a * ww) / ww.sum()
    b = b - np.sum(b * ww) / ww.sum()
    return float(np.sum(ww * a * b) / np.sqrt(np.sum(ww * a * a) * np.sum(ww * b * b)))


def rmse(m2, o2, mask, w):
    _check(m2, o2, mask)
    return float(np.sqrt(np.sum(w[mask] * (m2[mask] - o2[mask]) ** 2) / w[mask].sum()))


def _fractions(binary, valid, n):
    if n == 1:
        return np.where(valid, binary, 0.0)
    num = ndimage.uniform_filter(np.where(valid, binary, 0.0), size=n, mode="constant")
    den = ndimage.uniform_filter(valid.astype(float), size=n, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, 0.0)


def fss(m, o, mask, threshold, n):
    """Fractions skill score pooled over days (Roberts & Lean 2008).

    m, o: (day, y, x); neighbourhood of n x n grid points; cells outside `mask`
    are excluded from both the neighbourhood fractions and the score.
    Returns NaN when neither field exceeds the threshold anywhere (score undefined).
    """
    _check(m, o, mask)
    num = den = 0.0
    for md, od in zip(m, o):
        fm = _fractions((md >= threshold).astype(float), mask, n)
        fo = _fractions((od >= threshold).astype(float), mask, n)
        num += np.sum((fm[mask] - fo[mask]) ** 2)
        den += np.sum(fm[mask] ** 2 + fo[mask] ** 2)
    return float(1.0 - num / den) if den > 0 else float("nan")


def fss_useful(o, mask, threshold):
    """FSS target for a 'useful' scale: 0.5 + f0/2, f0 = observed base rate."""
    f0 = np.mean(o[..., mask] >= threshold)
    return 0.5 + f0 / 2.0


def _xy_km(lat, lon):
    la0 = np.radians(np.mean(lat))
    y = R_KM * np.radians(lat)[:, None] * np.ones(len(lon))[None, :]
    x = R_KM * np.cos(la0) * np.radians(lon)[None, :] * np.ones(len(lat))[:, None]
    return x, y


def sal(m2, o2, mask, lat, lon, f=1.0 / 15.0):
    """Structure, Amplitude, Location (Wernli et al. 2008) for one 2-D field pair.

    Objects: 8-connected regions with R >= f * R95, where R95 is the 95th
    percentile of the wet (>0.1 mm) cells of that field inside the mask.
    """
    _check(m2, o2, mask)
    x, y = _xy_km(lat, lon)
    xs, ys = x[mask], y[mask]
    d = np.hypot(xs.max() - xs.min(), ys.max() - ys.min())   # largest distance in the domain

    def props(r2):
        r = np.where(mask, r2, 0.0)
        tot = r.sum()
        cx, cy = (r * x).sum() / tot, (r * y).sum() / tot
        wet = r[mask][r[mask] > 0.1]
        rstar = f * np.percentile(wet, 95) if wet.size else np.inf
        lab, nobj = ndimage.label(r >= rstar, structure=np.ones((3, 3)))
        rn, vn, dist = [], [], []
        for k in range(1, nobj + 1):
            sel = lab == k
            rk = r[sel].sum()
            rn.append(rk)
            vn.append(rk / r[sel].max())
            dist.append(np.hypot((r[sel] * x[sel]).sum() / rk - cx, (r[sel] * y[sel]).sum() / rk - cy))
        rn = np.array(rn)
        V = float(np.sum(rn * np.array(vn)) / rn.sum()) if rn.size else 0.0
        rdist = float(np.sum(rn * np.array(dist)) / rn.sum()) if rn.size else 0.0
        return r[mask].mean(), cx, cy, V, rdist

    mm, mx, my, mV, mr = props(m2)
    om, ox, oy, oV, orr = props(o2)
    A = (mm - om) / (0.5 * (mm + om))
    S = (mV - oV) / (0.5 * (mV + oV)) if (mV + oV) > 0 else float("nan")
    L1 = np.hypot(mx - ox, my - oy) / d
    L2 = 2.0 * abs(mr - orr) / d
    return dict(S=float(S), A=float(A), L=float(L1 + L2), L1=float(L1), L2=float(L2))


def max_location_error_km(m2, o2, mask, lat, lon):
    """Great-circle distance between the cells holding the maximum of each field."""
    _check(m2, o2, mask)
    mm = np.where(mask, m2, -np.inf)
    oo = np.where(mask, o2, -np.inf)
    im = np.unravel_index(np.argmax(mm), mm.shape)
    io = np.unravel_index(np.argmax(oo), oo.shape)
    p1, p2 = np.radians([lat[im[0]], lon[im[1]]]), np.radians([lat[io[0]], lon[io[1]]])
    h = np.sin((p2[0] - p1[0]) / 2) ** 2 + np.cos(p1[0]) * np.cos(p2[0]) * np.sin((p2[1] - p1[1]) / 2) ** 2
    return float(2 * R_KM * np.arcsin(np.sqrt(h)))


def peak_ratio(m, o, mask):
    """Ratio of the largest daily cell value, model / observed."""
    _check(m, o, mask)
    return float(np.max(m[..., mask]) / np.max(o[..., mask]))


def q99_ratio(m, o, mask):
    """Ratio of the 99th percentile of all daily cell values in the box."""
    _check(m, o, mask)
    return float(np.percentile(m[..., mask], 99) / np.percentile(o[..., mask], 99))
