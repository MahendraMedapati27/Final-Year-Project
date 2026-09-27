"""Geometry simplification experiments (Part A3)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from shapely import make_valid, set_precision

try:
    from shapely import coverage_invalid_edges, coverage_is_valid, coverage_simplify

    HAS_COV = True
except ImportError:
    HAS_COV = False

from rainfall.config import resolve_path
from rainfall.geo import EQUAL_AREA_CRS, WGS84, build_districts_master, load_lgd_parquet

logger = logging.getLogger(__name__)


def diagnose_coverage(gdf: gpd.GeoDataFrame) -> dict:
    if not HAS_COV:
        return {"valid": None, "note": "coverage API unavailable"}
    geoms = list(gdf.geometry)
    valid = coverage_is_valid(geoms)
    edges = coverage_invalid_edges(geoms) if not valid else []
    return {"valid": bool(valid), "n_invalid_edges": len(edges)}


def try_precision_simplify(gdf: gpd.GeoDataFrame, tolerance: float = 0.007) -> tuple[gpd.GeoDataFrame, bool]:
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.apply(lambda g: make_valid(g) if g is not None else g)
    if not HAS_COV:
        return gdf, False
    try:
        prec = [set_precision(g, grid_size=1e-6) for g in gdf.geometry]
        simp = coverage_simplify(prec, tolerance)
        gdf["geometry"] = simp
        return gdf, True
    except Exception as exc:
        logger.warning("precision+coverage_simplify failed: %s", exc)
        return gdf, False


def gap_overlap_area(gdf_orig: gpd.GeoDataFrame, gdf_simp: gpd.GeoDataFrame) -> dict:
    ea_o = gdf_orig.to_crs(EQUAL_AREA_CRS)
    ea_s = gdf_simp.to_crs(EQUAL_AREA_CRS)
    from shapely.ops import unary_union

    u_o = unary_union(ea_o.geometry)
    u_s = unary_union(ea_s.geometry)
    gap = u_o.difference(u_s).area / 1e6
    overlap = u_s.difference(u_o).area / 1e6
    return {"gap_km2": gap, "extra_km2": overlap}


def zoom_simplification_figure(gdf_orig: gpd.GeoDataFrame, gdf_simp: gpd.GeoDataFrame, out: Path) -> None:
    # Kerala / Karnataka border approx bbox
    bbox = (74.5, 11.5, 77.5, 13.5)
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    for ax, g, title in zip(axes, [gdf_orig, gdf_simp], ["Unsimplified", "Simplified"]):
        g.plot(ax=ax, linewidth=0.3, edgecolor="black", facecolor="none")
        ax.set_xlim(bbox[0], bbox[2])
        ax.set_ylim(bbox[1], bbox[3])
        ax.set_title(title)
        ax.set_aspect("equal")
    fig.suptitle("Kerala/Karnataka border (300% zoom context)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def unsimplified_render_timing(gdf: gpd.GeoDataFrame) -> float:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    t0 = time.perf_counter()
    fig, ax = plt.subplots(figsize=(10, 11))
    polys = []
    for g in gdf.geometry:
        if g.geom_type == "Polygon":
            polys.append(np.asarray(g.exterior.coords))
        elif g.geom_type == "MultiPolygon":
            for p in g.geoms:
                polys.append(np.asarray(p.exterior.coords))
    pc = PolyCollection(polys, facecolors="lightgray", edgecolors="k", linewidths=0.1)
    ax.add_collection(pc)
    ax.autoscale()
    ax.set_aspect("equal")
    fig.canvas.draw()
    plt.close(fig)
    return time.perf_counter() - t0


def run_simplify_decision(skip_simplify: bool = True) -> dict:
    """Rebuild GPKG; default skip simplification if fast enough."""
    cand = resolve_path("data/geo/candidates/india-geodata/LGD_Districts.parquet")
    gdf = load_lgd_parquet(cand)
    diag = diagnose_coverage(gdf)
    outline = resolve_path("data/geo/candidates/india-soi.geojson")

    render_sec = unsimplified_render_timing(gdf)
    decision = {
        "coverage_valid": diag.get("valid"),
        "n_invalid_edges": diag.get("n_invalid_edges", 0),
        "unsimplified_poly_render_sec": render_sec,
        "skip_simplify": skip_simplify or render_sec < 2.0,
    }

    if decision["skip_simplify"]:
        # patch build to use tol=0 effectively - rebuild via geo module
        from rainfall.geo import _dissolve_districts

        gdf_d = _dissolve_districts(gdf)
        # write without simplify by calling build with internal flag - use simplify_tol=0
        build_districts_master(gdf_d, outline, simplify_tol=0.0)
        decision["method"] = "none (unsimplified)"
    else:
        gdf_s, ok = try_precision_simplify(gdf, 0.003)
        if not ok:
            gdf_s = gdf.copy()
            gdf_s["geometry"] = gdf_s.geometry.simplify(0.003, preserve_topology=True)
        metrics = gap_overlap_area(gdf, gdf_s)
        decision.update(metrics)
        decision["method"] = "per-geometry simplify 0.003 deg"
        zoom_simplification_figure(
            gdf, gdf_s, resolve_path("outputs/figures/geometry_simplification_check.png")
        )
    return decision
