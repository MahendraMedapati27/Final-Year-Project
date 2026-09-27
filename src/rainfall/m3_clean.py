"""Memory-efficient M3 clean with checkpoints."""

from __future__ import annotations

import json
from typing import Any
import shutil
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from rainfall.classes import daily_intensity_class, departure_category, guarded_departure
from rainfall.clean import relabel_unknown
from rainfall.config import load_config, resolve_path
from rainfall.dedupe import vectorized_dedupe
from rainfall.features import IMD_SEASON, parse_period_strings
from rainfall.hydrology_matrix import (
    build_paint_group_matrix,
    calendar_index,
    monsoon_cumulative,
    rolling_sum_nan_strict,
    spells_and_since_rain,
)
from rainfall.io import load_parquet, write_stage_manifest
from rainfall.memory_log import log_step, rss_mb
from rainfall.names import district_key, normalize_district, normalize_state
from rainfall.validate_crosswalk import load_imd_gist


def _matrix_features_long(
    paint_to_idx: dict[int, int],
    idx_to_pg: dict[int, int],
    dates: pd.DatetimeIndex,
    present: np.ndarray,
    mats: dict[str, np.ndarray],
) -> pd.DataFrame:
    pi_idx, di_idx = np.where(present)
    data: dict[str, Any] = {
        "paint_group_uid": [idx_to_pg[int(pi)] for pi in pi_idx],
        "date": [dates[int(di)] for di in di_idx],
    }
    for name, mat in mats.items():
        vals = mat[pi_idx, di_idx]
        if name == "monsoon_cum_complete":
            data[name] = vals.astype(bool)
        else:
            v2 = vals.astype(float)
            v2[(name.endswith("_len") or name == "days_since_rain") & (vals < 0)] = np.nan
            data[name] = v2
    return pd.DataFrame(data)


def enrich_dataframe(df: pd.DataFrame, cw: pd.DataFrame, pg_poly: pd.DataFrame) -> pd.DataFrame:
    cfg = load_config()
    guard_d = float(cfg["cleaning"]["min_normal_mm_daily"])
    guard_m = float(cfg["cleaning"]["min_normal_mm_monthly"])
    guard_c = float(cfg["cleaning"]["min_normal_mm_cumulative"])
    extreme = float(cfg["cleaning"]["extreme_mm"])

    gdf = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="districts")
    cent = gdf.set_index("shp_id")
    for c in ("lgd_state_code", "lgd_district_code"):
        if c not in gdf.columns:
            gdf[c] = np.nan

    df = parse_period_strings(df)
    df["state_std"] = df["state"].astype(str).map(normalize_state)
    df["district_std"] = [normalize_district(d, s) for d, s in zip(df["district"], df["state"])]
    df["district_key"] = [district_key(s, d) for s, d in zip(df["state"], df["district"])]
    df["district_uid"] = df.groupby(["state", "district"], observed=True).ngroup().astype(np.int32) + 1

    meta = cw[
        [
            "dataset_state",
            "dataset_district",
            "paint_group_uid",
            "shp_id",
            "match_method",
            "match_score",
            "area_km2_total",
            "resolution",
        ]
    ].rename(columns={"dataset_state": "state", "dataset_district": "district"})
    df = df.merge(meta, on=["state", "district"], how="left", suffixes=("", "_cw"))
    df["resolution"] = df["resolution"].fillna("direct")

    df["year"] = df["date"].dt.year.astype(np.int16)
    df["month"] = df["date"].dt.month.astype(np.int8)
    df["day"] = df["date"].dt.day.astype(np.int8)
    df["doy"] = df["date"].dt.dayofyear.astype(np.int16)
    df["iso_week"] = df["date"].dt.isocalendar().week.astype(np.int16)
    df["season"] = df["month"].map(IMD_SEASON).astype("category")
    df["is_monsoon"] = df["month"].isin([6, 7, 8, 9])
    df["monsoon_year"] = np.where(df["month"] >= 6, df["year"], df["year"] - 1)
    june1 = pd.to_datetime(df["monsoon_year"].astype(str) + "-06-01")
    df["monsoon_day"] = (df["date"] - june1).dt.days
    df.loc[df["monsoon_day"] < 0, "monsoon_day"] = np.nan

    df["qc_negative_fixed"] = False
    mneg = df["daily_actual_mm"] < 0
    df.loc[mneg, "qc_negative_fixed"] = True
    df.loc[mneg, "daily_actual_mm"] = np.nan
    if "monthly_actual_mm_provided" in df.columns:
        mnegm = df["monthly_actual_mm_provided"] < 0
        df.loc[mnegm, "monthly_actual_mm_provided"] = np.nan

    df["qc_extreme_actual"] = df["daily_actual_mm"] > extreme
    df["qc_missing_actual"] = df["daily_actual_mm"].isna()
    df["qc_missing_normal"] = df["daily_normal_mm"].isna()
    df["qc_departure_undefined"] = df["daily_normal_mm"].lt(guard_d) | df["daily_normal_mm"].isna()
    df["qc_no_geometry"] = df["shp_id"].isna()
    df["qc_placeholder_district"] = df["district"].astype(str).str.contains("Unknown Districts", case=False, na=False)
    if "qc_relabelled_unknown" not in df.columns:
        df["qc_relabelled_unknown"] = False
    if "qc_dup_unresolvable" not in df.columns:
        df["qc_dup_unresolvable"] = False

    df["daily_anomaly_mm"] = df["daily_actual_mm"] - df["daily_normal_mm"]
    df["daily_departure_pct"] = guarded_departure(df["daily_actual_mm"], df["daily_normal_mm"], guard_d)
    labels, codes = daily_intensity_class(df["daily_actual_mm"])
    df["daily_intensity_class"] = labels
    df["daily_intensity_code"] = codes
    df["daily_departure_cat"] = departure_category(df["daily_departure_pct"])
    df["daily_departure_cat_provided"] = df["daily_category_provided"]
    df["daily_departure_cat_agrees"] = df["daily_departure_cat"] == df["daily_departure_cat_provided"]

    df["monthly_departure_pct"] = guarded_departure(
        df["monthly_actual_mm_provided"], df["monthly_normal_mm_provided"], guard_m
    )
    df["monthly_departure_cat"] = departure_category(df["monthly_departure_pct"])
    df["monthly_departure_cat_provided"] = df["monthly_category_provided"]
    df["monthly_departure_cat_agrees"] = df["monthly_departure_cat"] == df["monthly_departure_cat_provided"]

    matrix_df = df.copy()
    matrix_df["paint_group_uid"] = matrix_df["paint_group_uid"].astype(float)
    pgs = sorted([int(x) for x in matrix_df["paint_group_uid"].dropna().unique() if int(x) > 0])
    paint_to_idx = {pg: i for i, pg in enumerate(pgs)}
    idx_to_pg = {i: pg for pg, i in paint_to_idx.items()}
    dates = calendar_index()

    log_step("matrix_build")
    actual, normal, present = build_paint_group_matrix(matrix_df, paint_to_idx, dates)
    rain3 = rolling_sum_nan_strict(actual, present, 3)
    rain7 = rolling_sum_nan_strict(actual, present, 7)
    rain30 = rolling_sum_nan_strict(actual, present, 30)
    mon_cum, mon_complete = monsoon_cumulative(actual, present, dates)
    mon_cum_n, _ = monsoon_cumulative(normal, present, dates)
    dry, wet, dsr = spells_and_since_rain(actual, present)

    mats = {
        "rain_3d_mm": rain3,
        "rain_7d_mm": rain7,
        "rain_30d_mm": rain30,
        "monsoon_cum_mm": mon_cum,
        "monsoon_cum_normal_mm": mon_cum_n,
        "monsoon_cum_complete": mon_complete.astype(np.float32),
        "dry_spell_len": dry.astype(np.float32),
        "wet_spell_len": wet.astype(np.float32),
        "days_since_rain": dsr.astype(np.float32),
    }
    fdf = _matrix_features_long(paint_to_idx, idx_to_pg, dates, present, mats)
    df = df.merge(fdf, on=["paint_group_uid", "date"], how="left", suffixes=("", "_mx"))
    for c in fdf.columns:
        if c in ("paint_group_uid", "date"):
            continue
        mx = f"{c}_mx"
        if mx in df.columns:
            df[c] = df[mx].combine_first(df[c] if c in df.columns else np.nan)
            df.drop(columns=[mx], inplace=True, errors="ignore")

    df["is_rainy_day"] = df["daily_actual_mm"] >= 2.5
    df["is_heavy_day"] = df["daily_actual_mm"] >= 64.5
    df["is_very_heavy_day"] = df["daily_actual_mm"] >= 115.6

    df["cum_departure_pct"] = guarded_departure(df["monsoon_cum_mm"], df["monsoon_cum_normal_mm"], guard_c)
    df["cum_departure_cat"] = departure_category(df["cum_departure_pct"])
    df["cum_departure_cat_provided"] = df["cumulative_category_provided"]
    df["cum_departure_cat_agrees"] = df["cum_departure_cat"] == df["cum_departure_cat_provided"]
    tol = 0.5
    df["monsoon_cum_agrees"] = np.isclose(
        df["monsoon_cum_mm"], df["cumulative_actual_mm_provided"], rtol=0, atol=tol, equal_nan=True
    )
    if "monsoon_cum_complete_mx" in df.columns:
        df.drop(columns=["monsoon_cum_complete_mx"], inplace=True, errors="ignore")
    if "monsoon_cum_complete" in df.columns:
        df["monsoon_cum_complete"] = df["monsoon_cum_complete"].astype(bool)

    if "area_km2_total" in df.columns:
        df["area_km2"] = df["area_km2_total"].astype(np.float32)
    else:
        df["area_km2"] = df["paint_group_uid"].map(cw.set_index("paint_group_uid")["area_km2_total"]).astype(np.float32)
    df["centroid_lon"] = df["shp_id"].map(cent["centroid_lon"] if "centroid_lon" in cent else cent.geometry.centroid.x)
    df["centroid_lat"] = df["shp_id"].map(cent["centroid_lat"] if "centroid_lat" in cent else cent.geometry.centroid.y)
    df["lgd_state_code"] = df["shp_id"].map(cent["lgd_state_code"] if "lgd_state_code" in cent.columns else np.nan)
    df["lgd_district_code"] = df["shp_id"].map(cent["lgd_district_code"] if "lgd_district_code" in cent.columns else np.nan)

    from rainfall.dedupe import _prepare_districts_for_weights
    from libpysal.weights import Queen

    gdf_w = _prepare_districts_for_weights(gdf)
    w = Queen.from_dataframe(gdf_w, use_index=False, ids=gdf_w["shp_id"].astype(int).tolist())
    n_neigh = {int(k): len(v) for k, v in w.neighbors.items()}
    df["n_neighbours"] = df["shp_id"].map(n_neigh).astype(np.float32)
    df["daily_volume_mcm"] = (df["daily_actual_mm"] * df["area_km2"] / 1000.0).astype(np.float32)

    float_cols = [
        "daily_actual_mm",
        "daily_normal_mm",
        "daily_departure_pct",
        "daily_anomaly_mm",
        "rain_3d_mm",
        "rain_7d_mm",
        "rain_30d_mm",
        "monsoon_cum_mm",
        "monsoon_cum_normal_mm",
    ]
    for c in float_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], downcast="float")

    from rainfall.extremes import apply_map_column, build_extreme_review

    review = build_extreme_review(df)
    df = apply_map_column(df, review)

    return df


def _write_enriched_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, path, compression="zstd", use_dictionary=True)


def run_m3_fresh(sample: bool = False) -> Path:
    t0 = time.perf_counter()
    cfg = load_config()
    ckpt = resolve_path("data/processed/checkpoints")
    if ckpt.exists():
        shutil.rmtree(ckpt)
    ckpt.mkdir(parents=True, exist_ok=True)

    log_step("load_parquet")
    df = load_parquet(sample=sample)
    n_raw = len(df)
    imd = load_imd_gist()
    df = relabel_unknown(df, imd)

    primary = pd.read_csv(resolve_path("outputs/tables/district_primary_obj_id.csv"))
    cw = pd.read_csv(resolve_path(cfg["paths"]["crosswalk"]))
    pg_poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))

    deduped_path = ckpt / "deduped.parquet"
    dup_log_path = resolve_path("outputs/tables/duplicates_resolved.csv")
    if deduped_path.exists() and dup_log_path.exists():
        deduped = pd.read_parquet(deduped_path)
        dstats = json.loads((ckpt / "dedupe_stats.json").read_text()) if (ckpt / "dedupe_stats.json").exists() else {}
        log_step("dedupe_resume_checkpoint", {"rows": len(deduped)})
    else:
        deduped, dup_log, dstats = vectorized_dedupe(df, primary, cw)
        dup_log.to_csv(dup_log_path, index=False)
        deduped.to_parquet(deduped_path, compression="zstd", index=False)
        (ckpt / "dedupe_stats.json").write_text(json.dumps(dstats, default=str), encoding="utf-8")

    enriched = enrich_dataframe(deduped, cw, pg_poly)
    out_path = resolve_path(cfg["paths"]["processed_enriched"])
    _write_enriched_parquet(enriched, out_path)

    from rainfall.m3_finalize import run_finalize

    run_finalize()

    manifest = {
        "stage": "clean_fresh",
        "n_raw": n_raw,
        "n_enriched": len(enriched),
        "n_removed_dupes": n_raw - len(enriched),
        "dedupe_stats": dstats,
        "wall_s": time.perf_counter() - t0,
        "peak_rss_mb": rss_mb(),
        "outputs": {"enriched": str(out_path), "deduped": str(deduped_path)},
    }
    mp = resolve_path("logs/run_manifest.json")
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    (resolve_path("outputs/checkpoints/p1_clean.json")).write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    log_step("clean_fresh_done", manifest)
    return out_path


def run_m3(years: list[int] | None = None, sample: bool = False) -> Path:
    if years is None and not sample:
        return run_m3_fresh(sample=False)
    # legacy year-chunk path
    t0 = time.perf_counter()
    cfg = load_config()
    ckpt = resolve_path("data/processed/checkpoints")
    ckpt.mkdir(parents=True, exist_ok=True)
    df = load_parquet(sample=sample)
    n_raw = len(df)
    primary = pd.read_csv(resolve_path("outputs/tables/district_primary_obj_id.csv"))
    cw = pd.read_csv(resolve_path(cfg["paths"]["crosswalk"]))
    pg_poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    deduped_path = ckpt / "deduped.parquet"
    if deduped_path.exists():
        deduped = pd.read_parquet(deduped_path)
        dstats = {}
    else:
        imd = load_imd_gist()
        df = relabel_unknown(df, imd)
        deduped, dup_log, dstats = vectorized_dedupe(df, primary, cw)
        dup_log.to_csv(resolve_path("outputs/tables/duplicates_resolved.csv"), index=False)
        deduped.to_parquet(deduped_path, compression="zstd", index=False)
    df = deduped[deduped["date"].dt.year.isin(years)] if years else deduped
    enriched = enrich_dataframe(df, cw, pg_poly)
    out_path = ckpt / f"enriched_{years[0]}.parquet" if years else resolve_path(cfg["paths"]["processed_enriched"])
    _write_enriched_parquet(enriched, out_path)
    log_step("write_enriched", {"path": str(out_path), "rows": len(enriched), "wall_s": time.perf_counter() - t0})
    return out_path


def merge_year_checkpoints() -> Path:
    cfg = load_config()
    ckpt = resolve_path("data/processed/checkpoints")
    parts = sorted(ckpt.glob("enriched_*.parquet"))
    if not parts:
        raise FileNotFoundError("No enriched_YYYY.parquet checkpoints")
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    out = resolve_path(cfg["paths"]["processed_enriched"])
    _write_enriched_parquet(df, out)
    from rainfall.m3_finalize import run_finalize

    run_finalize()
    return out
