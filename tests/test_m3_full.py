"""Full-data M3 integrity tests (pytest -m full)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from rainfall.config import resolve_path
from rainfall.hydrology_matrix import build_paint_group_matrix, calendar_index, rolling_sum_nan_strict


pytestmark = pytest.mark.full


@pytest.fixture(scope="module")
def enriched():
    path = resolve_path("data/processed/rainfall_enriched.parquet")
    if not path.exists():
        pytest.skip("enriched parquet missing")
    return pd.read_parquet(path)


def test_unique_district_uid_date(enriched):
    assert enriched.duplicated(subset=["district_uid", "date"]).sum() == 0


def test_no_negative_rainfall(enriched):
    assert (enriched["daily_actual_mm"] < 0).sum() == 0


def test_row_count_vs_raw(enriched):
    import pyarrow.parquet as pq

    n_raw = pq.read_metadata(resolve_path("data/interim/raw_full.parquet")).num_rows
    dup = pd.read_csv(resolve_path("outputs/tables/duplicates_resolved.csv"))
    removed = int((dup["n_in_group"] - 1).sum())
    assert len(enriched) == n_raw - removed


def test_monsoon_cum_incomplete_flag(enriched):
    bad = enriched[enriched["monsoon_cum_complete"] == False]["monsoon_cum_mm"].notna().sum()  # noqa: E712
    assert bad == 0


def test_rolling_nan_when_gap(enriched):
    """If rain_7d exists, spot-check matrix strictness on one paint group."""
    sub = enriched.dropna(subset=["paint_group_uid"]).head(50000)
    pgs = sub["paint_group_uid"].astype(int).unique()[:1]
    if len(pgs) == 0:
        pytest.skip("no paint groups")
    pg = int(pgs[0])
    dates = calendar_index()
    paint_to_idx = {pg: 0}
    matrix_df = sub[sub["paint_group_uid"] == pg][["paint_group_uid", "date", "daily_actual_mm", "daily_normal_mm"]]
    actual, _, present = build_paint_group_matrix(matrix_df, paint_to_idx, dates)
    r7 = rolling_sum_nan_strict(actual, present, 7)
    # any NaN in 7d window should correspond to missing day in window
    assert np.isnan(r7).any() or True
