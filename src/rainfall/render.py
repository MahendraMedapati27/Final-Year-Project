"""Daily choropleth rendering (M4 trial)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PolyCollection
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch

from rainfall.classes import INTENSITY_BOUNDS, INTENSITY_LABELS
from rainfall.config import load_config, resolve_path

logger = logging.getLogger(__name__)

IMD_COLORS = ["#F0F0F0", "#C6E6F5", "#7FC4E8", "#2E86C1", "#1B4F9C", "#6A1B9A", "#C62828"]
OUTSIDE_FILL = "#E8E4DC"
HATCH_NODATA = {"facecolor": "#F0F0F0", "edgecolor": "#999999", "hatch": "///", "linewidth": 0}


def explode_polygons(gdf: gpd.GeoDataFrame) -> tuple[list, np.ndarray, np.ndarray]:
    """Return polygon paths list, part_to_shp_id, shp_id order."""
    paths = []
    part_to_shp = []
    shp_ids = gdf["shp_id"].astype(int).values
    for i, geom in enumerate(gdf.geometry):
        sid = shp_ids[i]
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type == "Polygon":
            paths.append(np.asarray(geom.exterior.coords))
            part_to_shp.append(sid)
        elif geom.geom_type == "MultiPolygon":
            for p in geom.geoms:
                paths.append(np.asarray(p.exterior.coords))
                part_to_shp.append(sid)
    return paths, np.array(part_to_shp, dtype=np.int32), shp_ids


def build_render_matrix(enriched: pd.DataFrame, poly_map: pd.DataFrame) -> dict:
    from rainfall.classes import daily_intensity_class

    ac = "daily_actual_mm_map" if "daily_actual_mm_map" in enriched.columns else "daily_actual_mm"
    pg_day = enriched.groupby(["date", "paint_group_uid"], observed=True)[ac].first().reset_index()
    pg_day = pg_day.rename(columns={ac: "daily_actual_mm"})
    shp_ids = np.sort(poly_map["shp_id"].unique()).astype(int)
    pg_by_shp = poly_map.set_index("shp_id")["paint_group_uid"].astype(int).to_dict()
    shp_pg = pd.DataFrame({"shp_id": shp_ids, "paint_group_uid": [pg_by_shp.get(s, -1) for s in shp_ids]})
    merged = pg_day.merge(shp_pg, on="paint_group_uid", how="inner")
    dates = np.sort(merged["date"].unique())
    date_to_t = {d: i for i, d in enumerate(dates)}
    sid_to_j = {int(s): j for j, s in enumerate(shp_ids)}
    n_t, n_p = len(dates), len(shp_ids)
    values = np.full((n_t, n_p), np.nan, dtype=np.float32)
    class_idx = np.full((n_t, n_p), -1, dtype=np.int8)
    merged = merged.dropna(subset=["daily_actual_mm"])
    merged["ti"] = merged["date"].map(date_to_t)
    merged["sj"] = merged["shp_id"].map(sid_to_j)
    merged = merged.dropna(subset=["ti", "sj"])
    ti = merged["ti"].astype(int).values
    sj = merged["sj"].astype(int).values
    vals = merged["daily_actual_mm"].astype(np.float32).values
    values[ti, sj] = vals
    _, codes = daily_intensity_class(pd.Series(vals))
    class_idx[ti, sj] = codes.astype(np.int8).values
    np.savez_compressed(
        resolve_path("data/processed/render_matrix.npz"),
        dates=dates.astype("datetime64[D]"),
        shp_ids=shp_ids,
        values=values,
        class_idx=class_idx,
    )
    return {"dates": dates, "shp_ids": shp_ids, "values": values, "class_idx": class_idx}


def render_trial(date: pd.Timestamp, out_path: Path, cfg: dict) -> dict:
    matplotlib = __import__("matplotlib")
    matplotlib.use("Agg")

    gdf = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="districts")
    outline = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="india_outline")
    states = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="states")
    enriched = pd.read_parquet(
        resolve_path(cfg["paths"]["processed_enriched"]),
        filters=[("date", "=", pd.Timestamp(date))],
        columns=["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std", "area_km2"],
    )
    poly_map = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))

    paths, part_to_shp, _ = explode_polygons(gdf)
    pg_by_shp = poly_map.set_index("shp_id")["paint_group_uid"].to_dict()
    day = enriched.set_index("paint_group_uid")

    shp_class: dict[int, int] = {}
    shp_mm: dict[int, float] = {}
    for sid in np.unique(part_to_shp):
        pg = pg_by_shp.get(int(sid), -1)
        mm_col = "daily_actual_mm_map" if "daily_actual_mm_map" in day.columns else "daily_actual_mm"
        if pg not in day.index or pd.isna(day.loc[pg, mm_col]):
            shp_class[int(sid)] = -1
        else:
            from rainfall.classes import daily_intensity_class

            mm = float(day.loc[pg, mm_col])
            shp_mm[int(sid)] = mm
            _, c = daily_intensity_class(pd.Series([mm]))
            shp_class[int(sid)] = int(c.iloc[0])
    part_class = np.array([shp_class.get(int(s), -1) for s in part_to_shp], dtype=float)
    masked = np.ma.masked_where(part_class < 0, part_class)

    cmap = ListedColormap(IMD_COLORS)
    norm = BoundaryNorm(np.arange(-0.5, 7.5, 1), cmap.N)

    fw = float(cfg["render"]["figure_width_in"])
    fh = float(cfg["render"]["figure_height_in"])
    dpi = int(cfg["render"]["dpi"])
    fig, ax = plt.subplots(figsize=(fw, fh), dpi=dpi)

    # Outside districts: SOI outline minus union of districts
    from shapely.ops import unary_union

    district_union = unary_union(gdf.geometry)
    outside = outline.geometry.iloc[0].difference(district_union)
    if not outside.is_empty:
        gpd.GeoSeries([outside], crs=gdf.crs).plot(ax=ax, color=OUTSIDE_FILL, edgecolor="none")

    # Hatch base for nodata
    nodata_mask = part_class < 0
    if nodata_mask.any():
        nd_paths = [paths[i] for i in range(len(paths)) if nodata_mask[i]]
        pc_nd = PolyCollection(nd_paths, **HATCH_NODATA)
        ax.add_collection(pc_nd)

    valid_paths = [paths[i] for i in range(len(paths)) if not nodata_mask[i]]
    valid_vals = part_class[~nodata_mask]
    pc = PolyCollection(valid_paths, cmap=cmap, norm=norm, edgecolor="#555555", linewidth=float(cfg["render"]["district_linewidth"]))
    pc.set_array(valid_vals)
    ax.add_collection(pc)

    states.boundary.plot(ax=ax, color="#404040", linewidth=float(cfg["render"]["state_linewidth"]))
    outline.boundary.plot(ax=ax, color="#101010", linewidth=float(cfg["render"]["outline_linewidth"]))

    ax.set_xlim(68, 98)
    ax.set_ylim(6, 38)
    ax.set_aspect("equal")
    ax.axis("off")

    title = "District-wise Actual Rainfall over India"
    subtitle = f"Daily rainfall (mm) — {date.strftime('%A, %d %B %Y')}"
    ax.set_title(f"{title}\n{subtitle}", fontsize=12)

    district_classes = pd.Series([v for v in shp_class.values() if v >= 0])
    counts = district_classes.value_counts().sort_index()
    n_data_districts = len(district_classes)
    legend_patches = []
    for i, lab in enumerate(INTENSITY_LABELS):
        n = int(counts.get(i, 0))
        legend_patches.append(Patch(facecolor=IMD_COLORS[i], label=f"{lab} ({n})"))
    legend_patches.append(Patch(facecolor="#F0F0F0", hatch="///", label="No data"))
    ax.legend(handles=legend_patches, loc="lower left", fontsize=7, framealpha=0.9, bbox_to_anchor=(0.01, 0.08))

    mm_vals = pd.Series(list(shp_mm.values()))
    stats_txt = (
        f"Districts w/ data: {n_data_districts}  |  "
        f"Mean: {mm_vals.mean():.1f} mm  Max: {mm_vals.max():.1f} mm  "
        f"≥64.5 mm: {(mm_vals >= 64.5).sum()}"
        if len(mm_vals)
        else "No district rainfall this date"
    )
    ax.text(0.99, 0.04, stats_txt, transform=ax.transAxes, ha="right", va="bottom", fontsize=7, bbox=dict(boxstyle="round", facecolor="white", alpha=0.85))

    footnote = cfg["render"].get("paint_group_footnote", "")
    fig.text(0.5, 0.02, f"Data: IMD/MoES via NDAP · Boundaries: LGD/india-geodata 2026 · {footnote}", ha="center", fontsize=7)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    fig.canvas.draw()
    draw_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    fig.savefig(out_path, dpi=dpi, facecolor="white")
    elapsed = time.perf_counter() - t1
    plt.close(fig)
    from PIL import Image

    im = Image.open(out_path)
    return {
        "path": str(out_path),
        "size": im.size,
        "dpi": dpi,
        "seconds_save": elapsed,
        "seconds_draw": draw_s,
        "seconds_total": draw_s + elapsed,
        "file_kb": out_path.stat().st_size / 1024,
        "legend_class_sum": int(counts.sum()) if len(counts) else 0,
        "n_data_districts": n_data_districts,
    }


def wettest_day_2022_2025(enriched: pd.DataFrame) -> pd.Timestamp:
    sub = enriched[(enriched["date"] >= "2022-01-01") & (enriched["date"] <= "2025-12-31")]
    ac = "daily_actual_mm_map" if "daily_actual_mm_map" in enriched.columns else "daily_actual_mm"
    heavy = sub[sub[ac] >= 64.5].groupby("date", observed=True).size()
    if heavy.empty:
        return pd.Timestamp("2023-07-10")
    return pd.Timestamp(heavy.idxmax())


def run_trial_maps(cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_config()
    path = resolve_path(cfg["paths"]["processed_enriched"])
    poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    en_cols = pd.read_parquet(path, columns=["date", "paint_group_uid", "daily_actual_mm_map"])
    build_render_matrix(en_cols, poly)
    enriched = pd.read_parquet(path, columns=["date", "paint_group_uid", "daily_actual_mm", "state_std", "district_std"])
    out_dir = resolve_path("outputs/maps/trial")
    d1 = pd.Timestamp("2026-09-19")
    d2 = wettest_day_2022_2025(enriched)
    results = []
    for d in (d1, d2):
        p = out_dir / f"rainfall_actual_{d.date()}.png"
        results.append(render_trial(d, p, cfg))
    return results
