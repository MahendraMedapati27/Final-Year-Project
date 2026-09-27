"""Geometry candidates, scoring, and districts_master.gpkg (M2)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely import make_valid
from shapely.ops import unary_union

try:
    from shapely import coverage_simplify

    HAS_COVERAGE_SIMPLIFY = True
except ImportError:
    HAS_COVERAGE_SIMPLIFY = False

from rainfall.config import load_config, project_root, resolve_path
from rainfall.crosswalk import (
    dataset_target_latest,
    dataset_target_weighted,
    match_dataset_to_polygons,
)
from rainfall.io import load_parquet
from rainfall.names import district_key, normalize_district, normalize_state

logger = logging.getLogger(__name__)

EQUAL_AREA_CRS = "+proj=aea +lat_1=12 +lat_2=28 +lat_0=20 +lon_0=80 +datum=WGS84 +units=m"
WGS84 = "EPSG:4326"

CHECK_DISTRICTS = [
    ("Andhra Pradesh", "Alluri Sitharama Raju"),
    ("Andhra Pradesh", "Anakapalli"),
    ("Andhra Pradesh", "Annamayya"),
    ("Andhra Pradesh", "Bapatla"),
    ("Ladakh", "Leh"),
    ("Ladakh", "Kargil"),
    ("Lakshadweep", "Lakshadweep"),
    ("Andaman and Nicobar Islands", "Nicobars"),
]


def _pct_valid(geoms) -> float:
    n = len(geoms)
    if n == 0:
        return 0.0
    ok = sum(g is not None and (not hasattr(g, "is_empty") or not g.is_empty) and g.is_valid for g in geoms)
    return 100.0 * ok / n


def _clean_name_pct(names: pd.Series) -> float:
    if len(names) == 0:
        return 0.0
    s = names.astype(str).str.strip()
    good = s.str.len() >= 3
    good &= ~s.str.contains(r"[#@|]", regex=True, na=False)
    good &= s.str.lower().ne("nan")
    good &= s.str.lower().ne("none")
    return 100.0 * good.mean()


def _standardize_gdf(
    gdf: gpd.GeoDataFrame,
    shp_id_col: str,
    state_col: str,
    district_col: str,
    state_code_col: str | None = None,
    dist_code_col: str | None = None,
    source: str = "",
) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    if gdf.crs is None:
        gdf = gdf.set_crs(WGS84)
    else:
        gdf = gdf.to_crs(WGS84)
    gdf["geometry"] = gdf.geometry.apply(lambda g: make_valid(g) if g is not None else g)
    gdf["shp_id"] = pd.to_numeric(gdf[shp_id_col], errors="coerce").astype("Int64")
    gdf["state_name"] = gdf[state_col].astype(str)
    gdf["district_name"] = gdf[district_col].astype(str)
    gdf["state_std"] = gdf["state_name"].map(normalize_state)
    gdf["district_std"] = gdf.apply(lambda r: normalize_district(r["district_name"], r["state_name"]), axis=1)
    gdf["lgd_state_code"] = gdf[state_code_col] if state_code_col and state_code_col in gdf.columns else np.nan
    gdf["lgd_district_code"] = gdf[dist_code_col] if dist_code_col and dist_code_col in gdf.columns else np.nan
    gdf["source"] = source
    gdf = gdf.dropna(subset=["shp_id"])
    gdf["shp_id"] = gdf["shp_id"].astype(int)
    return gdf


def load_lgd_parquet(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_parquet(path)
    return _standardize_gdf(gdf, "OBJECTID", "stname", "dtname", "stcode11", "dtcode11", "lgd_parquet")


def load_soi_parquet(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_parquet(path)
    gdf = gdf.reset_index(drop=True)
    gdf["OBJECTID"] = np.arange(1, len(gdf) + 1)
    return _standardize_gdf(gdf, "OBJECTID", "STATE", "District", "STATE_C", "District_C", "soi_parquet")


def load_bhuvan_parquet(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_parquet(path)
    gdf = gdf.reset_index(drop=True)
    gdf["OBJECTID"] = np.arange(1, len(gdf) + 1)
    return _standardize_gdf(gdf, "OBJECTID", "s_name", "d_name", "s_code", "d_code", "bhuvan_parquet")


def load_datta07(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    gdf = gdf[~gdf["district"].astype(str).str.strip().isin(["", "nan", "None"])]
    return _standardize_gdf(gdf, "objectid", "state", "district", "st_code", "dist_code", "datta07")


def load_imd(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    dist_col = "District" if "District" in gdf.columns else "FULL_NAME"
    st_col = "STATE" if "STATE" in gdf.columns else "State_LGD"
    oid = "id" if "id" in gdf.columns else gdf.index.name or "objectid"
    if oid not in gdf.columns:
        gdf = gdf.reset_index(drop=False)
        oid = "id" if "id" in gdf.columns else gdf.columns[0]
    return _standardize_gdf(gdf, oid, st_col, dist_col, "State_LGD", None, "imd_2024")


def load_guneetnarula(path: Path) -> gpd.GeoDataFrame | None:
    if not path.exists():
        return None
    try:
        gdf = gpd.read_file(path)
    except Exception as e:
        logger.warning("guneetnarula load failed: %s", e)
        return None
    return _standardize_gdf(gdf, gdf.columns[0], "STATE", "DISTRICT", None, None, "guneetnarula")


def _dissolve_districts(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    agg = {
        "state_name": "first",
        "district_name": "first",
        "state_std": "first",
        "district_std": "first",
        "lgd_state_code": "first",
        "lgd_district_code": "first",
        "source": "first",
    }
    out = gdf.dissolve(by="shp_id", aggfunc=agg).reset_index()
    return gpd.GeoDataFrame(out, geometry="geometry", crs=gdf.crs)


def _check_special_districts(gdf: gpd.GeoDataFrame) -> dict[str, bool]:
    keys = set(zip(gdf["state_std"], gdf["district_std"]))
    raw_keys = set(zip(gdf["state_name"].str.upper(), gdf["district_name"].str.upper()))
    out = {}
    for st, dist in CHECK_DISTRICTS:
        sk, dk = district_key(st, dist)
        out[f"{dist} ({st})"] = (sk, dk) in keys or (st.upper(), dist.upper()) in raw_keys
    return out


def score_candidate(gdf: gpd.GeoDataFrame, targets_latest: pd.DataFrame, targets_all: pd.DataFrame) -> dict[str, Any]:
    gdf = _dissolve_districts(gdf)
    valid_pct = _pct_valid(gdf.geometry)
    name_pct = _clean_name_pct(gdf["district_name"])
    special = _check_special_districts(gdf)

    _, st_latest = match_dataset_to_polygons(gdf, targets_latest)
    _, st_all = match_dataset_to_polygons(gdf, targets_all)

    rl = st_latest.rates()
    ra = st_all.rates()
    return {
        "features": len(gdf),
        "pct_valid_geom": round(valid_pct, 2),
        "pct_clean_names": round(name_pct, 2),
        "special_districts": special,
        "latest_exact_pct": round(rl["exact_pct"], 2),
        "latest_norm_pct": round(rl["normalized_pct"], 2),
        "latest_fuzzy92_pct": round(rl["fuzzy92_pct"], 2),
        "latest_unmatched_pct": round(rl["unmatched_pct"], 2),
        "all_norm_pct": round(ra["normalized_pct"], 2),
        "all_fuzzy92_pct": round(ra["fuzzy92_pct"], 2),
        "all_unmatched_pct": round(ra["unmatched_pct"], 2),
    }


def _simplify_coverage(gdf: gpd.GeoDataFrame, tolerance: float) -> gpd.GeoDataFrame:
    if tolerance <= 0:
        return gdf.copy()
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.apply(lambda g: make_valid(g) if g is not None else g)
    if not HAS_COVERAGE_SIMPLIFY:
        logger.warning("shapely.coverage_simplify unavailable; using per-geometry simplify")
        gdf["geometry"] = gdf.geometry.simplify(tolerance, preserve_topology=True)
        return gdf
    try:
        geoms = list(gdf.geometry)
        simplified = coverage_simplify(geoms, tolerance)
        gdf["geometry"] = simplified
        return gdf
    except Exception as exc:
        logger.warning("coverage_simplify failed (%s); falling back to per-geometry simplify", exc)
        gdf["geometry"] = gdf.geometry.simplify(tolerance, preserve_topology=True)
        return gdf


def build_districts_master(
    gdf: gpd.GeoDataFrame,
    india_outline_path: Path,
    simplify_tol: float = 0.007,
) -> Path:
    cfg = load_config()
    out_path = resolve_path(cfg["paths"]["geo_districts"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig_dir = resolve_path(cfg["outputs"]["figures"])
    fig_dir.mkdir(parents=True, exist_ok=True)

    gdf = _dissolve_districts(gdf)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf = gdf.reset_index(drop=True)
    gdf["district_uid"] = np.arange(1, len(gdf) + 1, dtype=np.int32)

    gdf_ea = gdf.to_crs(EQUAL_AREA_CRS)
    gdf["area_km2"] = (gdf_ea.geometry.area / 1e6).astype(float)
    cent = gdf.to_crs(EQUAL_AREA_CRS).geometry.centroid.to_crs(WGS84)
    gdf["centroid_lon"] = cent.x.astype(float)
    gdf["centroid_lat"] = cent.y.astype(float)

    gdf_raw = gdf.copy()
    gdf_simp = _simplify_coverage(gdf, simplify_tol)

    # Plot simplification check
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    gdf_raw.plot(ax=axes[0], linewidth=0.1, edgecolor="black", facecolor="none")
    axes[0].set_title("Before coverage_simplify")
    gdf_simp.plot(ax=axes[1], linewidth=0.1, edgecolor="black", facecolor="none")
    axes[1].set_title(f"After (tol={simplify_tol})")
    for ax in axes:
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(fig_dir / "geometry_simplification_check.png", dpi=120)
    plt.close(fig)

    states = gdf_simp.dissolve(by="state_std", aggfunc={"state_name": "first"}).reset_index()

    outline = gpd.read_file(india_outline_path)
    if outline.crs is None:
        outline = outline.set_crs(WGS84)
    outline = outline.to_crs(WGS84)

    gdf_simp.to_file(out_path, layer="districts", driver="GPKG")
    gpd.GeoDataFrame(states, geometry="geometry", crs=gdf_simp.crs).to_file(
        out_path, layer="states", driver="GPKG", mode="a"
    )
    outline.to_file(out_path, layer="india_outline", driver="GPKG", mode="a")

    # Overview map
    fig, ax = plt.subplots(figsize=(10, 10))
    gdf_simp.assign(_c=gdf_simp["state_std"].astype("category").cat.codes).plot(
        column="_c", ax=ax, linewidth=0.08, edgecolor="0.3", legend=False, cmap="tab20"
    )
    ax.set_title("Districts by state (simplified)")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(fig_dir / "geometry_overview.png", dpi=150)
    plt.close(fig)

    logger.info("Wrote %s", out_path)
    return out_path


def run_geo_pipeline() -> dict[str, Any]:
    root = project_root()
    cand = root / "data" / "geo" / "candidates"
    df = load_parquet(sample=False)
    targets_latest = dataset_target_latest(df)
    targets_all = dataset_target_weighted()

    loaders: list[tuple[str, Callable[[], gpd.GeoDataFrame | None]]] = [
        ("India Geodata LGD parquet", lambda: load_lgd_parquet(cand / "india-geodata" / "LGD_Districts.parquet")),
        ("India Geodata SOI parquet", lambda: load_soi_parquet(cand / "india-geodata" / "SOI_Districts.parquet")),
        ("India Geodata Bhuvan parquet", lambda: load_bhuvan_parquet(cand / "india-geodata" / "bhuvan_districts.parquet")),
        ("datta07 GeoJSON", lambda: load_datta07(cand / "datta07" / "INDIA_DISTRICTS.geojson")),
        ("IMD 2024 gist", lambda: load_imd(cand / "imd" / "indian-districts-simplified.json")),
        (
            "guneetnarula 2019",
            lambda: load_guneetnarula(cand / "guneetnarula" / "india_districts.geojson"),
        ),
    ]

    scores = []
    candidate_gdfs: dict[str, gpd.GeoDataFrame] = {}

    for name, loader in loaders:
        try:
            gdf = loader()
        except Exception as e:
            logger.error("%s failed: %s", name, e)
            scores.append({"candidate": name, "error": str(e)})
            continue
        if gdf is None:
            scores.append({"candidate": name, "error": "not available"})
            continue
        sc = score_candidate(gdf, targets_latest, targets_all)
        sc["candidate"] = name
        scores.append(sc)
        candidate_gdfs[name] = _dissolve_districts(gdf)

    scores_df = pd.DataFrame(scores)
    tables = resolve_path("outputs/tables")
    tables.mkdir(parents=True, exist_ok=True)
    scores_df.to_csv(tables / "geometry_candidate_scores.csv", index=False)

    report_lines = [
        "# Geometry candidate comparison",
        "",
        "India Geodata release `admin/districts` assets (11): "
        "bhuvan_districts.{geojsonl.7z,parquet,pmtiles}, LGD_Districts.{geojsonl.7z,parquet,pmtiles}, "
        "SOI_Districts.{geojsonl.7z,parquet,pmtiles}. Evaluated parquet layers + datta07 + IMD gist + guneetnarula.",
        "",
        scores_df.to_markdown(index=False),
    ]
    resolve_path("outputs/reports").mkdir(parents=True, exist_ok=True)
    (resolve_path("outputs/reports/geometry_candidates.md")).write_text("\n".join(report_lines), encoding="utf-8")

    eligible = [s for s in scores if "latest_fuzzy92_pct" in s and s["latest_fuzzy92_pct"] >= 98.0]
    if not eligible:
        eligible = [s for s in scores if "latest_fuzzy92_pct" in s]
    pick = max(
        eligible,
        key=lambda s: (s.get("pct_clean_names", 0), s.get("latest_fuzzy92_pct", 0)),
    )
    best_name = pick["candidate"]
    best_rate = pick["latest_fuzzy92_pct"]
    best_gdf = candidate_gdfs[best_name]
    if best_rate < 98.0:
        logger.warning("Best latest match rate %.2f%% below 98%% threshold", best_rate)

    assert best_gdf is not None
    outline = cand / "india-soi.geojson"
    gpkg = build_districts_master(best_gdf, outline)

    from rainfall.crosswalk import append_resolved_aliases, build_crosswalk_from_gpkg

    cw_path = build_crosswalk_from_gpkg(gpkg)
    cw = pd.read_csv(cw_path)
    append_resolved_aliases(cw)

    result = {
        "chosen": best_name,
        "best_latest_fuzzy92_pct": best_rate,
        "gpkg": str(gpkg),
        "crosswalk": str(cw_path),
        "scores": scores,
    }
    (resolve_path("logs/geo_manifest.json")).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(scores_df.to_string(index=False))
    print(f"\nChosen: {best_name} ({best_rate:.2f}% latest fuzzy>=92)")
    return result
