"""Duplicate resolution with neighbour reference for large conflicts."""

from __future__ import annotations

import json
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from libpysal.weights import Queen

from rainfall.config import load_config, resolve_path
from rainfall.memory_log import log_step
from rainfall.names import normalize_district, normalize_state

VALUE_COLS = [
    "daily_actual_mm",
    "daily_normal_mm",
    "weekly_actual_mm_provided",
    "cumulative_actual_mm_provided",
    "monthly_actual_mm_provided",
]


def _prepare_districts_for_weights(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.ops import unary_union

    gdf = gdf[gdf.geometry.notna()].copy()
    fixed = []
    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            fixed.append(geom)
            continue
        if geom.geom_type == "GeometryCollection":
            parts = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
            geom = unary_union(parts) if parts else geom
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            geom = geom.buffer(0)
        fixed.append(geom)
    gdf["geometry"] = fixed
    gdf = gdf[~gdf.geometry.is_empty]
    return gdf


def _load_queen_neighbors() -> dict[int, list[int]]:
    cfg = load_config()
    gdf = _prepare_districts_for_weights(gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="districts"))
    w = Queen.from_dataframe(gdf, use_index=False, ids=gdf["shp_id"].astype(int).tolist())
    return {int(k): [int(n) for n in w.neighbors[k]] for k in w.neighbors}


def _shp_to_district(cw: pd.DataFrame) -> dict[int, tuple[str, str]]:
    m: dict[int, tuple[str, str]] = {}
    for _, r in cw.dropna(subset=["shp_id"]).iterrows():
        m[int(r["shp_id"])] = (r["dataset_state"], r["dataset_district"])
    return m


def _resolve_conflict(
    a: float,
    b: float,
    ref_r: float | None,
) -> tuple[float | None, str]:
    lo, hi = min(a, b), max(a, b)
    if abs(a - b) <= max(2.0, 0.2 * hi):
        return (a + b) / 2.0, "conflict_mean_small"
    if ref_r is None or np.isnan(ref_r):
        return None, "conflict_unresolvable_no_ref"
    da, db = abs(a - ref_r), abs(b - ref_r)
    thresh = max(25.0, 2.0 * abs(ref_r)) if ref_r else 25.0
    if da > thresh and db > thresh:
        if ref_r is not None and not np.isnan(ref_r):
            return (a if da <= db else b), "conflict_distrust_pick"
        return None, "conflict_unresolvable_far"
    return (a if da <= db else b), "conflict_neighbour_pick"


def vectorized_dedupe(
    df: pd.DataFrame,
    primary: pd.DataFrame,
    cw: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    log_step("dedupe_start", {"rows": len(df)})
    key = ["state", "district", "date"]
    pref = primary.set_index(["state", "district"])["primary_obj_id"].to_dict()
    neigh = _load_queen_neighbors()
    shp_dist = _shp_to_district(cw)
    dist_shp = cw.dropna(subset=["shp_id"]).set_index(["dataset_state", "dataset_district"])["shp_id"].astype(int).to_dict()

    work = df.copy()
    work["_has_actual"] = work["daily_actual_mm"].notna().astype(np.int8)
    pref_df = primary[["state", "district", "primary_obj_id"]].rename(columns={"primary_obj_id": "_pref_obj"})
    work = work.merge(pref_df, on=["state", "district"], how="left")
    work["_pref_oid"] = (work["obj_id"] == work["_pref_obj"]).astype(np.int8)
    work["_nn"] = work[VALUE_COLS].notna().sum(axis=1).astype(np.int16)
    work = work.sort_values(
        key + ["_has_actual", "_pref_oid", "_nn"],
        ascending=[True, True, True, False, False, False],
    )

    dup_mask = work.duplicated(subset=key, keep=False)
    singles = work[~dup_mask].copy()
    singles["qc_dup_resolved"] = False
    singles["qc_dup_conflict"] = False
    singles["qc_dup_unresolvable"] = False

    ref: dict[tuple[str, str, pd.Timestamp], float] = {}
    for _, r in singles.iterrows():
        if pd.notna(r["daily_actual_mm"]):
            ref[(r["state"], r["district"], pd.Timestamp(r["date"]))] = float(r["daily_actual_mm"])

    logs: list[dict] = []
    kept_rows: list[pd.DataFrame] = [singles]

    def neighbour_median(st: str, dist: str, dt: pd.Timestamp) -> float | None:
        sid = dist_shp.get((st, dist))
        if sid is None:
            return None
        nbrs = neigh.get(int(sid), [])
        vals = []
        for ns in nbrs:
            pair = shp_dist.get(ns)
            if not pair:
                continue
            v = ref.get((pair[0], pair[1], dt))
            if v is not None:
                vals.append(v)
        return float(np.median(vals)) if vals else None

    for k, grp in work[dup_mask].groupby(key, observed=True):
        grp = grp.copy()
        st, dist, dt = k[0], k[1], pd.Timestamp(k[2])
        pool = grp[grp["daily_actual_mm"].notna()]
        rule = "fallback"
        kept = grp.iloc[0]
        if len(pool) == 0:
            kept = grp.iloc[0]
            rule = "all_nan_first"
        elif len(pool) == 1:
            kept = pool.iloc[0]
            rule = "non_null_actual"
        else:
            pref_oid = pref.get((st, dist))
            if pref_oid is not None and (pool["obj_id"] == pref_oid).any():
                kept = pool[pool["obj_id"] == pref_oid].iloc[0]
                rule = "preferred_obj_id"
            else:
                kept = pool.sort_values("_nn", ascending=False).iloc[0]
                rule = "most_nonnull_cols"

        kept = kept.copy()
        kept["qc_dup_resolved"] = True
        kept["qc_dup_conflict"] = False
        kept["qc_dup_unresolvable"] = False
        nonnull = grp["daily_actual_mm"].dropna()
        ref_r = None
        val_a = val_b = np.nan
        if len(nonnull) > 1 and nonnull.nunique() > 1:
            u = np.sort(nonnull.unique())
            val_a, val_b = float(u[0]), float(u[-1])
            ref_r = neighbour_median(st, dist, dt)
            chosen, rule = _resolve_conflict(val_a, val_b, ref_r)
            if rule == "conflict_mean_small":
                kept["daily_actual_mm"] = chosen
                kept["qc_dup_conflict"] = True
            elif rule.startswith("conflict_neighbour"):
                kept["daily_actual_mm"] = chosen
                kept["qc_dup_conflict"] = True
            else:
                kept["daily_actual_mm"] = np.nan
                kept["qc_dup_unresolvable"] = True
                rule = "conflict_unresolvable"

        if pd.notna(kept["daily_actual_mm"]):
            ref[(st, dist, dt)] = float(kept["daily_actual_mm"])

        logs.append(
            {
                "state": st,
                "district": dist,
                "date": dt,
                "rule": rule,
                "n_in_group": len(grp),
                "val_a": val_a,
                "val_b": val_b,
                "ref_r": ref_r,
                "chosen": kept["daily_actual_mm"],
                "kept_obj_id": kept.get("obj_id"),
                "dropped_obj_ids": grp.drop(kept.name)["obj_id"].tolist(),
            }
        )
        kept_rows.append(pd.DataFrame([kept]))

    out = pd.concat(kept_rows, ignore_index=True)
    out.drop(columns=["_has_actual", "_pref_oid", "_nn", "_pref_obj"], inplace=True, errors="ignore")

    log_df = pd.DataFrame(logs)
    stats = {
        "groups": len(log_df),
        "rules": log_df["rule"].value_counts().to_dict() if len(log_df) else {},
        "n_removed": int(len(df) - len(out)),
    }
    conf = log_df[log_df["rule"].str.contains("conflict", na=False)]
    diffs = []
    for _, r in conf.iterrows():
        if pd.notna(r["val_a"]) and pd.notna(r["val_b"]) and pd.notna(r["chosen"]):
            diffs.append(max(abs(r["val_a"] - r["chosen"]), abs(r["val_b"] - r["chosen"])))
    stats["conflict_median_mm"] = float(np.median(diffs)) if diffs else 0.0
    stats["conflict_max_mm"] = float(np.max(diffs)) if diffs else 0.0
    log_step("dedupe_end", {"rows": len(out), **stats})
    return out, log_df, stats
