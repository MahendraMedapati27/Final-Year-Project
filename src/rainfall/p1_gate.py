"""P1 gate printer and no_data / outside-area reports."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union

from rainfall.config import load_config, resolve_path
from rainfall.spatial_validate import run_spatial_validation
from rainfall.unknown_districts import run_unknown_report
from rainfall.verify import run_verify


def report_no_data_polygons() -> pd.DataFrame:
    poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    nd = poly[poly["resolution"] == "no_data"].copy()
    cfg = load_config()
    gdf = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="districts")
    gdf = gdf.to_crs("+proj=aea +lat_1=12 +lat_2=28 +lat_0=20 +lon_0=80 +datum=WGS84 +units=m")
    india_area = gdf.geometry.area.sum() / 1e6
    rows = []
    for _, r in nd.iterrows():
        sid = int(r["shp_id"])
        row = gdf[gdf["shp_id"] == sid]
        area = float(row.geometry.area.iloc[0] / 1e6) if len(row) else np.nan
        rows.append(
            {
                "state": r.get("lgd_state", row["state_name"].iloc[0] if len(row) else ""),
                "lgd_name": r.get("lgd_district", row["district_name"].iloc[0] if len(row) else ""),
                "shp_id": sid,
                "area_km2": area,
                "pct_india_district_area": 100 * area / india_area if india_area else np.nan,
                "assignment": "no_data",
                "reason": "historical CSV not in repo; containment vs IMD not run in gate",
            }
        )
    rep = pd.DataFrame(rows)
    rep.to_csv(resolve_path("outputs/tables/no_data_polygons_report.csv"), index=False)
    return rep


def report_outside_district_area() -> dict:
    cfg = load_config()
    gdf = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="districts").to_crs(4326)
    outline = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="india_outline").to_crs(4326)
    ea = "+proj=aea +lat_1=12 +lat_2=28 +lat_0=20 +lon_0=80 +datum=WGS84 +units=m"
    du = unary_union(gdf.geometry)
    outside = outline.geometry.iloc[0].difference(du)
    outside_g = gpd.GeoSeries([outside], crs=4326).to_crs(ea)
    area_km2 = float(outside_g.area.iloc[0] / 1e6)
    india_km2 = float(outline.to_crs(ea).geometry.area.iloc[0] / 1e6)
    payload = {"outside_km2": area_km2, "pct_of_soi": 100 * area_km2 / india_km2, "note": "SOI outline minus union(districts)"}
    Path(resolve_path("outputs/checkpoints/p1_outside_area.json")).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def print_dedupe_summary() -> None:
    dup = pd.read_csv(resolve_path("outputs/tables/duplicates_resolved.csv"))
    print("Dedupe methods:\n", dup["rule"].value_counts().to_string())
    en = pd.read_parquet(resolve_path("data/processed/rainfall_enriched.parquet"), columns=["date", "daily_actual_mm", "state", "district"])
    heavy_before = en[en["daily_actual_mm"] > 500]
    print(f"Rows >500mm now: {len(heavy_before)}")
    print("Top 10 daily_actual_mm:\n", en.nlargest(10, "daily_actual_mm")[["date", "state", "district", "daily_actual_mm"]].to_string(index=False))


def run_p1_gate() -> dict:
    v = run_verify()
    checklist = pd.read_csv(resolve_path("outputs/tables/schema_checklist.csv"))
    spatial = run_spatial_validation()
    run_unknown_report()
    nd = report_no_data_polygons()
    outside = report_outside_district_area()
    payload = {"verify": v, "spatial_failures": int((~spatial["inside_state"]).sum()), "no_data_count": len(nd), **outside}
    Path(resolve_path("outputs/checkpoints/p1_gate.json")).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload
