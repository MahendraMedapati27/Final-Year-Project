"""Paint groups: map LGD polygons to dataset districts (Part A2)."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from rainfall.config import load_config, resolve_path
from rainfall.geo import EQUAL_AREA_CRS, WGS84
from rainfall.io import load_parquet
from rainfall.names import normalize_state
from rainfall.validate_crosswalk import load_imd_gist

logger = logging.getLogger(__name__)


def _primary_obj_ids(df: pd.DataFrame) -> pd.Series:
    sub = df.dropna(subset=["obj_id"]).copy()
    sub["obj_id"] = sub["obj_id"].astype(int)
    return sub.groupby(["state", "district"], observed=True)["obj_id"].agg(
        lambda s: int(s.mode().iloc[0]) if len(s.mode()) else int(s.iloc[0])
    )


def _historical_parent(lgd_name: str, state_name: str) -> tuple[str, str] | None:
    hist = resolve_path("data/geo/candidates/historical/New_districts_created_1951_to_2024.csv")
    if not hist.exists():
        return None
    newd = pd.read_csv(hist)
    nm = str(lgd_name).strip().upper()
    st = normalize_state(state_name)
    hit = newd[newd["New District"].astype(str).str.upper().str.strip() == nm]
    if hit.empty:
        return None
    row = hit.iloc[-1]
    parent_raw = str(row.get("Old districts", "")).split(",")[0].strip()
    parent_state = str(row.get("State/UT", state_name))
    if not parent_raw:
        return None
    return parent_state, parent_raw


def assign_orphan_polygons(
    orphans: gpd.GeoDataFrame,
    imd: gpd.GeoDataFrame,
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Map orphan LGD polygons to dataset district via IMD parent containment."""
    imd_ea = imd.to_crs(EQUAL_AREA_CRS)
    orph_ea = orphans.to_crs(EQUAL_AREA_CRS)
    oid_primary = _primary_obj_ids(df)
    imd_by_oid = imd_ea.dropna(subset=["obj_id"]).drop_duplicates("obj_id").set_index("obj_id")

    rows = []
    for _, poly in orph_ea.iterrows():
        shp_id = int(poly["shp_id"])
        pg_area = poly.geometry.area
        if pg_area <= 0:
            rows.append({"shp_id": shp_id, "parent_state": None, "parent_district": None, "method": "no_data", "frac": 0})
            continue
        best = None
        for (st, dist), oid in oid_primary.items():
            if int(oid) not in imd_by_oid.index:
                continue
            imd_g = imd_by_oid.loc[int(oid), "geometry"]
            inter = poly.geometry.intersection(imd_g).area
            frac = inter / pg_area
            if frac >= 0.5 and (best is None or frac > best[0]):
                best = (frac, st, dist, int(oid))
        if best:
            rows.append(
                {
                    "shp_id": shp_id,
                    "parent_state": best[1],
                    "parent_district": best[2],
                    "method": "imd_parent_containment",
                    "frac": best[0],
                    "parent_obj_id": best[3],
                }
            )
        else:
            hist = _historical_parent(poly.get("district_name", ""), poly.get("state_name", ""))
            if hist:
                rows.append(
                    {
                        "shp_id": shp_id,
                        "parent_state": hist[0],
                        "parent_district": hist[1],
                        "method": "historical_csv_parent",
                        "frac": 0,
                    }
                )
            else:
                rows.append(
                    {
                        "shp_id": shp_id,
                        "state_std": poly.get("state_std"),
                        "district_name": poly.get("district_name"),
                        "method": "no_data",
                        "frac": 0,
                        "reason": "no IMD parent >=50% overlap",
                    }
                )
    return pd.DataFrame(rows)


def build_paint_groups() -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = load_config()
    gpkg = resolve_path(cfg["paths"]["geo_districts"])
    cw_path = resolve_path(cfg["paths"]["crosswalk"])

    districts = gpd.read_file(gpkg, layer="districts")
    cw = pd.read_csv(cw_path)
    df = load_parquet(sample=False)
    imd = load_imd_gist()

    matched_ids = set(cw.dropna(subset=["shp_id"])["shp_id"].astype(int))
    orphans = districts[~districts["shp_id"].isin(matched_ids)].copy()
    orphan_assign = assign_orphan_polygons(orphans, imd, df)

    # paint_group_uid per dataset district
    cw = cw.copy()
    cw["paint_group_uid"] = np.arange(1, len(cw) + 1, dtype=np.int32)
    key_to_pg = {
        (r["dataset_state"], r["dataset_district"]): int(r["paint_group_uid"])
        for _, r in cw.iterrows()
        if pd.notna(r.get("shp_id"))
    }

    poly_rows = []
    for _, r in cw.dropna(subset=["shp_id"]).iterrows():
        poly_rows.append(
            {
                "shp_id": int(r["shp_id"]),
                "paint_group_uid": int(r["paint_group_uid"]),
                "resolution": "direct",
                "dataset_state": r["dataset_state"],
                "dataset_district": r["dataset_district"],
            }
        )

    for _, o in orphan_assign.iterrows():
        sid = int(o["shp_id"])
        if o["method"] in ("imd_parent_containment", "historical_csv_parent"):
            key = (o["parent_state"], o["parent_district"])
            pg = key_to_pg.get(key)
            if pg is None:
                continue
            poly_rows.append(
                {
                    "shp_id": sid,
                    "paint_group_uid": pg,
                    "resolution": f"child_of_{o['parent_district']}",
                    "dataset_state": o["parent_state"],
                    "dataset_district": o["parent_district"],
                }
            )
            cw.loc[
                (cw["dataset_state"] == o["parent_state"]) & (cw["dataset_district"] == o["parent_district"]),
                "resolution",
            ] = "direct_with_children"
        else:
            poly_rows.append(
                {
                    "shp_id": sid,
                    "paint_group_uid": -1,
                    "resolution": "no_data",
                    "dataset_state": None,
                    "dataset_district": None,
                    "reason": o.get("reason", "unassigned orphan"),
                }
            )

    cw["resolution"] = cw.get("resolution", "direct")
    cw.loc[cw["resolution"].isna(), "resolution"] = "direct"

    poly_map = pd.DataFrame(poly_rows)
    out_poly = resolve_path("data/processed/paint_group_polygons.csv")
    out_poly.parent.mkdir(parents=True, exist_ok=True)
    poly_map.to_csv(out_poly, index=False)
    cw.to_csv(cw_path, index=False)
    orphan_assign.to_csv(resolve_path(cfg["outputs"]["tables"]) / "orphan_polygon_assignment.csv", index=False)

    # Area sums per paint group
    ea = districts.to_crs(EQUAL_AREA_CRS)
    ea["area_km2"] = ea.geometry.area / 1e6
    pg_areas = poly_map.merge(ea[["shp_id", "area_km2"]], on="shp_id", how="left")
    pg_sum = pg_areas.groupby("paint_group_uid")["area_km2"].sum()
    cw["area_km2_total"] = cw["paint_group_uid"].map(pg_sum)

    cw.to_csv(cw_path, index=False)
    return cw, poly_map


def reconcile_counts() -> dict:
    df = load_parquet(sample=False)
    cfg = load_config()
    cw = pd.read_csv(resolve_path(cfg["paths"]["crosswalk"]))
    poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))

    all_pairs = df.groupby(["state", "district"], observed=True).ngroups
    ex_unk = (
        df[~df["district"].astype(str).str.contains("Unknown Districts", case=False, na=False)]
        .groupby(["state", "district"], observed=True)
        .ngroups
    )
    matched_pairs = cw[cw["shp_id"].notna()]["dataset_district"].count()
    n_poly_matched = len(poly[poly["resolution"] == "direct"]) + len(poly[poly["resolution"].str.startswith("child_of", na=False)])
    n_orphan_no = len(poly[poly["resolution"] == "no_data"])
    return {
        "unique_state_district_all": all_pairs,
        "unique_excluding_unknown": ex_unk,
        "crosswalk_rows": len(cw),
        "pairs_with_primary_polygon": int(cw["shp_id"].notna().sum()),
        "polygons_in_paint_groups": int(len(poly[poly["paint_group_uid"] > 0])),
        "polygons_no_data": n_orphan_no,
        "lgd_total_polygons": len(gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="districts")),
    }
