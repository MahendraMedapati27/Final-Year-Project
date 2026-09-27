"""M2 geometry and crosswalk tests."""

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

from rainfall.config import load_config, resolve_path
from rainfall.crosswalk import load_manual_overrides
from rainfall.names import normalize_state

GPKG = resolve_path(load_config()["paths"]["geo_districts"])
ISLAND_CHECKS = [
    ("LADAKH", "LEH"),
    ("LADAKH", "KARGIL"),
    ("LAKSHADWEEP", "LAKSHADWEEP"),
    ("ANDAMAN AND NICOBAR", "NICOBARS"),
]


@pytest.fixture(scope="module")
def districts() -> gpd.GeoDataFrame:
    assert GPKG.exists(), "Run: python -m rainfall.cli geo"
    return gpd.read_file(GPKG, layer="districts")


@pytest.fixture(scope="module")
def crosswalk() -> pd.DataFrame:
    path = resolve_path(load_config()["paths"]["crosswalk"])
    return pd.read_csv(path)


def test_polygons_valid(districts: gpd.GeoDataFrame) -> None:
    assert districts.crs is not None
    assert districts.geometry.is_valid.all()
    assert (districts["area_km2"] > 0).all()


def test_island_districts_present(districts: gpd.GeoDataFrame) -> None:
    keys = set(zip(districts["state_std"], districts["district_std"]))
    for sk, dk in ISLAND_CHECKS:
        assert (sk, dk) in keys, f"Missing island district {dk} ({sk})"


def test_one_polygon_one_dataset(crosswalk: pd.DataFrame) -> None:
    matched = crosswalk.dropna(subset=["shp_id"]).copy()
    matched["shp_id"] = matched["shp_id"].astype(int)
    dup = matched.groupby("shp_id").size()
    assert (dup <= 1).all()


def test_no_cross_state_matches(crosswalk: pd.DataFrame, districts: gpd.GeoDataFrame) -> None:
    poly = districts.set_index("shp_id")
    matched = crosswalk.dropna(subset=["shp_id"])
    for _, row in matched.iterrows():
        pid = int(row["shp_id"])
        pstate = poly.loc[pid, "state_std"]
        assert normalize_state(row["dataset_state"]) == pstate


def test_manual_overrides_applied(crosswalk: pd.DataFrame) -> None:
    manual = load_manual_overrides()
    for (st, dist), pid in manual.items():
        row = crosswalk[(crosswalk["dataset_state"] == st) & (crosswalk["dataset_district"] == dist)]
        assert len(row) == 1
        assert int(row.iloc[0]["shp_id"]) == pid


def test_match_rate_latest(crosswalk: pd.DataFrame) -> None:
    latest = pd.read_csv(resolve_path("outputs/tables/crosswalk_latest_date.csv"))
    rate = (latest["match_method"] != "unmatched").mean()
    assert rate >= 0.98
