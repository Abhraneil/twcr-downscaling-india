#!/usr/bin/env python3
"""Build the boundary lines drawn on every map (assets/boundaries/*.geojson).

    pip install shapely pyshp                    # only this script needs them
    python scripts/preprocess/make_boundaries.py --india india-composite.geojson \
        --states Admin2.shp --countries ne_10m_admin_0_countries_ind.shp

Inputs (see assets/boundaries/README.md for sources and licences):
  --india      DataMeet maps, Country/india-composite.geojson: India, its land boundary as depicted
               by the Survey of India, with a detailed coast (harbours and creeks)
  --states     DataMeet maps, States/Admin2.shp: the 36 states and union territories of India
               (only the lines between them are used: its coast includes harbours and creeks as land)
  --countries  Natural Earth 1:10m admin 0 countries, India point of view (_ind): only the
               countries other than India are used

Outputs, clipped to BBOX and simplified (Douglas-Peucker, tolerances below):
  india_outline.geojson   the coast and land boundary of India
  india_states.geojson    boundaries between states, ending at the coast
  neighbours.geojson      coasts and borders of the other countries, without their segments
                          along India's land boundary (drawn once, from the India outline)
The figures need only json and matplotlib to draw them (scripts/scoring/boundaries.py).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import shapefile
from shapely.geometry import box, mapping, shape
from shapely.ops import linemerge, unary_union

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "boundaries"
BBOX = (50.0, -5.0, 100.0, 40.0)        # lon_min, lat_min, lon_max, lat_max: every map in the repo
TOL_INDIA = 0.004                       # degrees (~0.4 km): good enough for the 3 km maps
TOL_OTHERS = 0.01                       # degrees (~1 km)
SEAM = 0.06                             # degrees: neighbour lines this close to India's land
                                        # boundary are dropped (the two sources differ slightly)


def lines(geom):
    """Boundary lines of a (multi)polygon, or the lines of a line geometry, as a list."""
    g = geom.boundary if geom.geom_type in ("Polygon", "MultiPolygon") else geom
    g = linemerge(g) if g.geom_type == "MultiLineString" else g
    if g.is_empty:
        return []
    return list(g.geoms) if hasattr(g, "geoms") else [g]


def write(name, geoms, source, licence, tol):
    clip = box(*BBOX)
    feats, npts = [], 0
    for g in geoms:
        g = g.intersection(clip)
        if g.geom_type in ("MultiLineString", "GeometryCollection"):
            g = linemerge([x for x in getattr(g, "geoms", [g]) if x.geom_type == "LineString"])
        g = g.simplify(tol, preserve_topology=False)
        for ln in lines(g):
            if ln.geom_type != "LineString" or ln.length < tol:
                continue
            c = [[round(x, 4), round(y, 4)] for x, y in ln.coords]
            npts += len(c)
            feats.append({"type": "Feature", "properties": {}, "geometry": {"type": "LineString", "coordinates": c}})
    fc = {"type": "FeatureCollection", "name": name,
          "description": f"{source}. Licence: {licence}. Clipped to lon {BBOX[0]}-{BBOX[2]}, lat {BBOX[1]}-{BBOX[3]}, "
                         f"simplified with a tolerance of {tol} deg by scripts/preprocess/make_boundaries.py.",
          "features": feats}
    f = OUT / f"{name}.geojson"
    f.write_text(json.dumps(fc, separators=(",", ":")) + "\n")
    print(f"{f.relative_to(ROOT)}: {len(feats)} lines, {npts} points, {f.stat().st_size / 1e3:.0f} kB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--india", type=Path, required=True)
    ap.add_argument("--states", type=Path, required=True)
    ap.add_argument("--countries", type=Path, required=True)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    r = shapefile.Reader(str(a.states))
    states = [shape(s.__geo_interface__) for s in r.shapes()]
    names = [rec["ST_NM"] for rec in r.records()]
    assert len(states) == 36 and all(g.is_valid for g in states), "expected 36 valid state polygons"
    union = unary_union(states)
    internal = unary_union([ln for g in states for ln in lines(g)]).difference(unary_union(lines(union)).buffer(1e-6))
    gj = json.loads(a.india.read_text())
    india = unary_union([shape(f["geometry"]) for f in gj["features"]])
    assert india.is_valid
    outline = unary_union(lines(india))
    internal = internal.intersection(india.buffer(0.01))     # end the state lines at this coast
    print(f"{len(names)} states and union territories; India bounds {[round(v, 2) for v in india.bounds]}")

    n = shapefile.Reader(str(a.countries))
    others = [shape(s.__geo_interface__) for s, rec in zip(n.shapes(), n.records()) if rec["ADM0_A3"] != "IND"]
    clip = box(*BBOX).buffer(1.0)
    others = [g if g.is_valid else g.buffer(0) for g in others if g.intersects(clip)]
    other_lines = unary_union([ln for g in others for ln in lines(g.intersection(clip))])
    # India's land boundary only (the outline away from the sea): where India touches a neighbour
    land_border = outline.intersection(unary_union(others).buffer(SEAM))
    other_lines = other_lines.difference(land_border.buffer(SEAM))

    write("india_outline", [outline], "DataMeet Community Maps Project, Country/india-composite.geojson "
          "(github.com/datameet/maps): India as per the official boundary of the Survey of India, compiled from "
          "LSIB (U.S. Department of State), Alhasan Systems and Natural Earth", "CC0", TOL_INDIA)
    write("india_states", [internal], "DataMeet Community Maps Project, States/Admin2 (github.com/datameet/maps), "
          "state boundaries from Election Commission of India maps",
          "CC BY 2.5 India (project page) / CC BY 4.0 (repository); attribution required", TOL_INDIA)
    write("neighbours", [other_lines], "Natural Earth 1:10m admin 0 countries, India point of view "
          "(ne_10m_admin_0_countries_ind)", "public domain", TOL_OTHERS)


if __name__ == "__main__":
    main()
