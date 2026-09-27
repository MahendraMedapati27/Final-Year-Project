"""Build render cache once (main process; uses GPKG)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection
from PIL import Image

from rainfall.config import load_config, resolve_path
from rainfall.frozen_layout import NODATA_RGB, OUTSIDE_RGB, render_config_hash, palette_rgb_uint8
from rainfall.palette_lab import OUTSIDE_FILL, PALETTE_HEX
from rainfall.render_daily import DailyMapRenderer, HATCH_NODATA
from rainfall.render_geom import load_render_geometry

logger = logging.getLogger(__name__)


def cache_dir(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    h = render_config_hash(cfg)
    p = resolve_path(f"outputs/render_cache/{h}")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _fig_size_px(cfg: dict) -> tuple[int, int, int, float, float]:
    rc = cfg["render"]
    dpi = int(rc["dpi"])
    fw = float(rc["figure_width_in"])
    fh = float(rc["figure_height_in"])
    w, h = int(fw * dpi), int(fh * dpi)
    return w, h, dpi, fw, fh


def _rgb_from_canvas(fig) -> np.ndarray:
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())
    return buf[:, :, :3].copy()


def build_cache(cfg: dict | None = None, force: bool = False) -> Path:
    cfg = cfg or load_config()
    out = cache_dir(cfg)
    meta_path = out / "meta.json"
    if meta_path.exists() and not force:
        return out

    geom = load_render_geometry(cfg, use_cache=False)
    w, h, dpi, fw, fh = _fig_size_px(cfg)

    # --- ID canvas (unique colour per polygon part, ax_main only) ---
    fig_id, ax = plt.subplots(figsize=(fw, fh), dpi=dpi)
    fig_id.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.11)
    ax = fig_id.add_axes([0.06, 0.15, 0.88, 0.74])
    ax.set_facecolor("white")
    ax.set_xlim(68, 97)
    ax.set_ylim(8, 37)
    ax.set_aspect("equal")
    ax.axis("off")
    n_parts = len(geom.paths)
    for i, path in enumerate(geom.paths):
        pid = i + 1
        r = (pid >> 16) & 255
        g = (pid >> 8) & 255
        b = pid & 255
        if r + g + b < 30:
            r = max(r, 40)
        ax.add_collection(
            PolyCollection(
                [path],
                facecolors=[(r / 255, g / 255, b / 255)],
                edgecolors="none",
                antialiased=False,
            )
        )
    id_rgb = _rgb_from_canvas(fig_id)
    plt.close(fig_id)
    id_map = np.zeros((h, w), dtype=np.int32)
    for i in range(n_parts):
        pid = i + 1
        r = (pid >> 16) & 255
        g = (pid >> 8) & 255
        b = pid & 255
        if r + g + b < 30:
            r = max(r, 40)
        mask = (id_rgb[:, :, 0] == r) & (id_rgb[:, :, 1] == g) & (id_rgb[:, :, 2] == b)
        id_map[mask] = pid
    np.save(out / "id_canvas.npy", id_map)
    np.save(out / "part_to_shp.npy", geom.part_to_shp.astype(np.int32))

    # --- Static base + lines via approved renderer (all no-data hatch hidden, all class 0) ---
    r0 = DailyMapRenderer(cfg=cfg, geom=geom)
    # Empty day: force all nodata for hatch template; separate pass for lines/base
    import pandas as pd

    empty = pd.DataFrame(columns=["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std"])
    r0.draw_date(pd.Timestamp("2021-01-01"), empty)
    all_nd = _rgb_from_canvas(r0.fig)

    # All class 0 (no rain) for static fill reference
    day0 = pd.read_parquet(
        resolve_path(cfg["paths"]["processed_enriched"]),
        filters=[("date", "=", pd.Timestamp("2021-01-31"))],
        columns=["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std", "qc_isolated_extreme"],
    )
    r0.draw_date(pd.Timestamp("2021-01-31"), day0)
    ref_rgb = _rgb_from_canvas(r0.fig)

    # Static base: hide text by whiting text bands (keep map only) — capture map-only render
    fig_s, ax_s = plt.subplots(figsize=(fw, fh), dpi=dpi)
    fig_s.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.11)
    ax_m = fig_s.add_axes([0.06, 0.15, 0.88, 0.74])
    import geopandas as gpd

    g = geom
    if not g.outside_geom.is_empty:
        gpd.GeoSeries([g.outside_geom], crs=g.gdf.crs).plot(ax=ax_m, color=OUTSIDE_FILL, edgecolor="none", zorder=0)
    g.gdf.plot(ax=ax_m, color=OUTSIDE_FILL, edgecolor="none", zorder=1, rasterized=True)
    g.state_boundary.plot(ax=ax_m, color="none", edgecolor="#404040", linewidth=float(cfg["render"]["state_linewidth"]), alpha=0.85, zorder=4)
    g.outline.boundary.plot(ax=ax_m, color="#101010", linewidth=float(cfg["render"]["outline_linewidth"]), zorder=5)
    ax_m.set_xlim(68, 97)
    ax_m.set_ylim(8, 37)
    ax_m.set_aspect("equal")
    ax_m.axis("off")
    base_map = _rgb_from_canvas(fig_s)
    plt.close(fig_s)

    # Full static lines overlay (RGBA): lines-only on white
    lines_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    lines_rgba[:, :, :3] = 255
    lines_rgba[:, :, 3] = 255
    diff = np.abs(ref_rgb.astype(np.int16) - base_map.astype(np.int16)).max(axis=2)
    # approximate: use approved all-nodata render for hatch layer
    np.save(out / "static_base_map.npy", base_map)
    np.save(out / "hatch_reference_rgb.npy", all_nd)
    np.save(out / "lines_approx_mask.npy", (diff > 8).astype(np.uint8))

    # Nodata hatch-only layer: render all paths as hatch
    fig_h, ax_h = plt.subplots(figsize=(fw, fh), dpi=dpi)
    ax_h = fig_h.add_axes([0.06, 0.15, 0.88, 0.74])
    ax_h.set_facecolor("white")
    if not g.outside_geom.is_empty:
        gpd.GeoSeries([g.outside_geom], crs=g.gdf.crs).plot(ax=ax_h, color=OUTSIDE_FILL, edgecolor="none")
    g.gdf.plot(ax=ax_h, color=OUTSIDE_FILL, edgecolor="none", rasterized=True)
    ax_h.add_collection(PolyCollection(geom.paths, **HATCH_NODATA, antialiased=False))
    g.state_boundary.plot(ax=ax_h, color="none", edgecolor="#404040", linewidth=0.5, alpha=0.85)
    g.outline.boundary.plot(ax=ax_h, color="#101010", linewidth=0.6)
    ax_h.set_xlim(68, 97)
    ax_h.set_ylim(8, 37)
    ax_h.set_aspect("equal")
    ax_h.axis("off")
    hatch_rgb = _rgb_from_canvas(fig_h)
    plt.close(fig_h)
    np.save(out / "nodata_layer_rgb.npy", hatch_rgb)

    palette = palette_rgb_uint8()
    np.save(out / "palette.npy", palette)

    shp_names = {}
    for _, row in geom.gdf.iterrows():
        shp_names[int(row["shp_id"])] = [str(row["state_name"]), str(row["district_name"])]
    (out / "shp_names.json").write_text(json.dumps(shp_names), encoding="utf-8")

    poly_map = __import__("pandas").read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    pg_by_shp = poly_map.set_index("shp_id")["paint_group_uid"].astype(int).to_dict()
    (out / "pg_by_shp.json").write_text(json.dumps({str(k): int(v) for k, v in pg_by_shp.items()}), encoding="utf-8")

    meta = {
        "hash": render_config_hash(cfg),
        "width": w,
        "height": h,
        "dpi": dpi,
        "figure_width_in": fw,
        "figure_height_in": fh,
        "n_parts": n_parts,
        "palette_hex": PALETTE_HEX,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    plt.close(r0.fig)
    logger.info("Render cache built at %s", out)
    return out
