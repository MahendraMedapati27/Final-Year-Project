"""Matplotlib paths with interior rings (fixes white holes in districts)."""

from __future__ import annotations

import numpy as np
from matplotlib.path import Path
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon


def _add_ring(verts: list, codes: list, coords) -> None:
    xys = list(coords)
    if len(xys) < 3:
        return
    verts.extend(xys)
    codes.extend([Path.MOVETO] + [Path.LINETO] * (len(xys) - 2) + [Path.CLOSEPOLY])


def shapely_to_mpath(geom) -> Path | None:
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, Polygon):
        verts: list = []
        codes: list = []
        _add_ring(verts, codes, geom.exterior.coords)
        for ring in geom.interiors:
            _add_ring(verts, codes, ring.coords)
        return Path(verts, codes) if verts else None
    if isinstance(geom, MultiPolygon):
        verts, codes = [], []
        for p in geom.geoms:
            sub = shapely_to_mpath(p)
            if sub is None:
                continue
            verts.extend(sub.vertices.tolist())
            codes.extend(sub.codes.tolist())
        return Path(verts, codes) if verts else None
    if isinstance(geom, GeometryCollection):
        verts, codes = [], []
        for g in geom.geoms:
            sub = shapely_to_mpath(g)
            if sub is None:
                continue
            verts.extend(sub.vertices.tolist())
            codes.extend(sub.codes.tolist())
        return Path(verts, codes) if verts else None
    return None


def explode_polygon_paths(gdf) -> tuple[list[Path], np.ndarray, np.ndarray]:
    paths: list[Path] = []
    part_to_shp: list[int] = []
    shp_ids = gdf["shp_id"].astype(int).values
    for i, geom in enumerate(gdf.geometry):
        sid = int(shp_ids[i])
        mp = shapely_to_mpath(geom)
        if mp is None:
            continue
        paths.append(mp)
        part_to_shp.append(sid)
    return paths, np.array(part_to_shp, dtype=np.int32), shp_ids
