"""P1b column and paint-group tests."""

from __future__ import annotations

import pandas as pd
import pytest

from rainfall.config import resolve_path


@pytest.mark.full
def test_daily_actual_mm_map_column():
    path = resolve_path("data/processed/rainfall_enriched.parquet")
    if not path.exists():
        pytest.skip("no enriched")
    cols = pd.read_parquet(path, columns=[]).columns.tolist() if hasattr(pd.read_parquet(path, columns=[]), "columns") else []
    import pyarrow.parquet as pq

    names = pq.read_schema(path).names
    assert "daily_actual_mm_map" in names
    assert "qc_isolated_extreme" in names
    df = pd.read_parquet(path, columns=["daily_actual_mm", "daily_actual_mm_map", "qc_isolated_extreme"])
    assert (df.loc[df["qc_isolated_extreme"], "daily_actual_mm_map"].isna()).all()
    assert (df.loc[df["qc_isolated_extreme"], "daily_actual_mm"].notna()).all()


@pytest.mark.full
def test_paint_group_area_sums():
    cw = pd.read_csv(resolve_path("data/processed/district_crosswalk.csv"))
    poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    import geopandas as gpd

    gdf = gpd.read_file(resolve_path("data/geo/districts_master.gpkg"), layer="districts")
    ea = gdf.to_crs("+proj=aea +lat_1=12 +lat_2=28 +lat_0=20 +lon_0=80 +datum=WGS84 +units=m")
    ea["area_km2"] = ea.geometry.area / 1e6
    merged = poly.merge(ea[["shp_id", "area_km2"]], on="shp_id")
    sums = merged.groupby("paint_group_uid")["area_km2"].sum()
    cw_area = cw.set_index("paint_group_uid")["area_km2_total"]
    for pg, s in sums.items():
        if pg <= 0:
            continue
        if pg in cw_area.index:
            assert abs(cw_area.loc[pg] - s) / s < 0.01
