"""Independent crosswalk validation (Part A1)."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from shapely.ops import unary_union

from rainfall.config import load_config, resolve_path
from rainfall.geo import EQUAL_AREA_CRS, WGS84
from rainfall.io import load_parquet
from rainfall.names import district_key, normalize_district, normalize_state

logger = logging.getLogger(__name__)


def load_imd_gist(path: Path | None = None) -> gpd.GeoDataFrame:
    path = path or resolve_path("data/geo/candidates/imd/indian-districts-simplified.json")
    gdf = gpd.read_file(path)
    gdf = gdf.to_crs(WGS84)
    id_col = "id" if "id" in gdf.columns else None
    st_col = "STATE" if "STATE" in gdf.columns else "State_LGD"
    dist_col = "District" if "District" in gdf.columns else "FULL_NAME"
    gdf["obj_id"] = pd.to_numeric(gdf[id_col], errors="coerce").astype("Int64")
    gdf["state_name"] = gdf[st_col].astype(str)
    gdf["district_name"] = gdf[dist_col].astype(str)
    gdf["state_std"] = gdf["state_name"].map(normalize_state)
    gdf["district_std"] = gdf.apply(lambda r: normalize_district(r["district_name"], r["state_name"]), axis=1)
    return gdf


def obj_id_name_agreement(df: pd.DataFrame, imd: gpd.GeoDataFrame) -> tuple[float, pd.DataFrame]:
    """Compare dataset (state, district, obj_id) with IMD polygon names."""
    sub = df.dropna(subset=["obj_id"]).copy()
    sub["obj_id"] = sub["obj_id"].astype(int)
    pairs = sub.groupby(["state", "district", "obj_id"], observed=True).size().reset_index(name="n")

    imd_by_id = imd.dropna(subset=["obj_id"]).drop_duplicates("obj_id", keep="first").set_index("obj_id")

    rows = []
    for _, row in pairs.iterrows():
        oid = int(row["obj_id"])
        if oid not in imd_by_id.index:
            rows.append({**row, "imd_district": None, "imd_state": None, "fuzzy_score": 0, "agrees": False})
            continue
        imd_row = imd_by_id.loc[oid]
        ds_st, ds_dist = row["state"], row["district"]
        sk, dk = district_key(ds_st, ds_dist)
        imd_sk = imd_row["state_std"]
        imd_dk = imd_row["district_std"]
        score = fuzz.WRatio(dk, imd_dk) if sk == imd_sk else 0
        if sk != imd_sk:
            score = max(score, fuzz.WRatio(normalize_state(ds_st), imd_sk) * 0.5)
        agrees = sk == imd_sk and score >= 90
        rows.append(
            {
                **row.to_dict(),
                "imd_district": imd_row["district_name"],
                "imd_state": imd_row["state_name"],
                "dataset_std": f"{sk}|{dk}",
                "imd_std": f"{imd_sk}|{imd_dk}",
                "fuzzy_score": score,
                "agrees": agrees,
            }
        )
    detail = pd.DataFrame(rows)
    rate = detail["agrees"].mean() if len(detail) else 0.0
    return float(rate), detail


def _iou(g1, g2) -> float:
    if g1 is None or g2 is None or g1.is_empty or g2.is_empty:
        return 0.0
    inter = g1.intersection(g2).area
    union = g1.union(g2).area
    return float(inter / union) if union > 0 else 0.0


def crosswalk_iou_validation(
    crosswalk: pd.DataFrame,
    lgd: gpd.GeoDataFrame,
    imd: gpd.GeoDataFrame,
    obj_id_detail: pd.DataFrame,
) -> pd.DataFrame:
    """IoU between LGD polygon (name crosswalk) and IMD polygon (obj_id)."""
    lgd = lgd.to_crs(EQUAL_AREA_CRS)
    imd_ea = imd.to_crs(EQUAL_AREA_CRS)
    imd_by_id = imd_ea.dropna(subset=["obj_id"]).drop_duplicates("obj_id").set_index("obj_id")

    # Primary obj_id per dataset district from mode of non-null obj_ids
    df = load_parquet(sample=False)
    oid_map = (
        df.dropna(subset=["obj_id"])
        .groupby(["state", "district"], observed=True)["obj_id"]
        .agg(lambda s: int(s.mode().iloc[0]) if len(s.mode()) else int(s.iloc[0]))
    )

    cw = crosswalk.dropna(subset=["shp_id"]).copy()
    cw["shp_id"] = cw["shp_id"].astype(int)
    lgd_idx = lgd.set_index("shp_id")

    rows = []
    for _, row in cw.iterrows():
        key = (row["dataset_state"], row["dataset_district"])
        oid = oid_map.get(key, np.nan)
        if pd.isna(oid) or int(oid) not in imd_by_id.index:
            continue
        sid = int(row["shp_id"])
        if sid not in lgd_idx.index:
            continue
        g_lgd = lgd_idx.loc[sid, "geometry"]
        g_imd = imd_by_id.loc[int(oid), "geometry"]
        iou = _iou(g_lgd, g_imd)
        rows.append(
            {
                "dataset_state": row["dataset_state"],
                "dataset_district": row["dataset_district"],
                "shp_id": sid,
                "obj_id": int(oid),
                "iou": iou,
                "suspect": iou < 0.5,
                "match_method": row.get("match_method"),
            }
        )
    return pd.DataFrame(rows)


def run_a1_validation() -> dict:
    cfg = load_config()
    df = load_parquet(sample=False)
    imd = load_imd_gist()
    agree_rate, detail = obj_id_name_agreement(df, imd)

    out_tables = resolve_path(cfg["outputs"]["tables"])
    out_tables.mkdir(parents=True, exist_ok=True)
    detail.to_csv(out_tables / "obj_id_name_agreement.csv", index=False)

    result = {"name_agreement_rate_pct": agree_rate * 100, "n_pairs": len(detail)}
    if agree_rate >= 0.90:
        cw = pd.read_csv(resolve_path(cfg["paths"]["crosswalk"]))
        lgd = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="districts")
        iou_df = crosswalk_iou_validation(cw, lgd, imd, detail)
        iou_df.to_csv(out_tables / "crosswalk_validation.csv", index=False)
        result["iou_median"] = float(iou_df["iou"].median()) if len(iou_df) else np.nan
        result["n_suspect"] = int(iou_df["suspect"].sum()) if len(iou_df) else 0
        result["path"] = str(out_tables / "crosswalk_validation.csv")
    else:
        cw = pd.read_csv(resolve_path(cfg["paths"]["crosswalk"]))
        review = cw[(cw["match_method"] != "exact") & (cw["match_score"] < 100)]
        review.to_csv(out_tables / "crosswalk_nonexact_review.csv", index=False)
        result["fallback_review"] = str(out_tables / "crosswalk_nonexact_review.csv")

    (resolve_path("outputs/reports/crosswalk_validation_summary.md")).write_text(
        f"# Crosswalk validation\n\n- Obj_Id name agreement: **{agree_rate*100:.2f}%** (n={len(detail)} distinct triples)\n",
        encoding="utf-8",
    )
    # Primary Obj_Id per district (max IoU with LGD shp from crosswalk)
    cw = pd.read_csv(resolve_path(cfg["paths"]["crosswalk"]))
    lgd = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="districts")
    lgd_ea = lgd.to_crs(EQUAL_AREA_CRS)
    imd_ea = imd.to_crs(EQUAL_AREA_CRS)
    imd_by_id = imd_ea.drop_duplicates("obj_id").set_index("obj_id")
    lgd_idx = lgd_ea.set_index("shp_id")
    primary_rows = []
    for _, row in cw.dropna(subset=["shp_id"]).iterrows():
        st, dist, sid = row["dataset_state"], row["dataset_district"], int(row["shp_id"])
        if sid not in lgd_idx.index:
            continue
        g_lgd = lgd_idx.loc[sid, "geometry"]
        oids = df[(df["state"] == st) & (df["district"] == dist)]["obj_id"].dropna().astype(int).unique()
        best_oid, best_iou = None, -1.0
        for oid in oids:
            if oid not in imd_by_id.index:
                continue
            iou = _iou(g_lgd, imd_by_id.loc[oid, "geometry"])
            if iou > best_iou:
                best_iou, best_oid = iou, int(oid)
        primary_rows.append(
            {
                "state": st,
                "district": dist,
                "shp_id": sid,
                "primary_obj_id": best_oid,
                "primary_obj_iou": best_iou,
            }
        )
    pd.DataFrame(primary_rows).to_csv(out_tables / "district_primary_obj_id.csv", index=False)
    result["primary_obj_id_table"] = str(out_tables / "district_primary_obj_id.csv")

    return result
