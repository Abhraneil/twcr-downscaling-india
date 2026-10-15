"""Area-weighted remapping of model precipitation onto the IMD 0.25 deg grid.

Method: every target cell is sampled with k x k sub-points spread uniformly over
the cell; each sub-point takes the value of the source cell whose centre is nearest
(great-circle, via a KD-tree on unit vectors) and the target value is the mean
over sub-points. With k at least twice the target/source spacing ratio this is a
first-order conservative remap to within sampling error (tested in
tests/test_remap.py), and the same code handles a finer source (3 and 12 km models)
and a coarser source (1 deg 20CRv3). Sub-points farther than `max_dist_km` from
any source centre (outside the model domain) give NaN.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

R_KM = 6371.0


def _xyz(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], axis=-1)


class Remapper:
    def __init__(self, src_lat2d, src_lon2d, tgt_lat1d, tgt_lon1d, src_dx_km, k=None, max_dist_km=None):
        tgt_dlat = float(np.diff(tgt_lat1d).mean())
        tgt_dlon = float(np.diff(tgt_lon1d).mean())
        tgt_dx_km = tgt_dlat * 111.2
        if k is None:
            k = int(max(4, np.ceil(2 * tgt_dx_km / src_dx_km)))
        self.k = k
        self.shape = (len(tgt_lat1d), len(tgt_lon1d))
        off = (np.arange(k) + 0.5) / k - 0.5
        la = (tgt_lat1d[:, None] + off[None, :] * tgt_dlat).ravel()          # (ny*k)
        lo = (tgt_lon1d[:, None] + off[None, :] * tgt_dlon).ravel()          # (nx*k)
        LA, LO = np.meshgrid(la, lo, indexing="ij")
        tree = cKDTree(_xyz(np.asarray(src_lat2d).ravel(), np.asarray(src_lon2d).ravel()))
        dist, idx = tree.query(_xyz(LA.ravel(), LO.ravel()))
        dist_km = dist * R_KM
        if max_dist_km is None:
            max_dist_km = 0.75 * src_dx_km * np.sqrt(2)
        self.idx = idx
        self.valid = dist_km <= max_dist_km
        self.sub_shape = LA.shape

    def __call__(self, field2d):
        v = np.asarray(field2d, dtype="float64").ravel()[self.idx]
        v = np.where(self.valid, v, np.nan)
        ny, nx = self.shape
        v = v.reshape(ny, self.k, nx, self.k)
        # NaN propagates: a target cell is valid only if fully covered by the source domain
        return v.mean(axis=(1, 3))
