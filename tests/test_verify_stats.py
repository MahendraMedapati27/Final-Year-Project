"""Independent stats vs reference implementation (sparse + dense synthetic days)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from rainfall.map_stats_independent import compute_day_manifest_stats
from rainfall.render_geom_cache import load_geometry_cached
from rainfall.config import load_config


def _synthetic_day(geom, pg_ids: list[int], mm_values: list[float], *, excl_pg: set[int] | None = None) -> pd.DataFrame:
    excl_pg = excl_pg or set()
    rows = []
    for pg, mm in zip(pg_ids, mm_values):
        rows.append(
            {
                "paint_group_uid": pg,
                "daily_actual_mm_map": mm,
                "state_std": "TestState",
                "district_std": f"D{pg}",
                "qc_isolated_extreme": pg in excl_pg,
            }
        )
    return pd.DataFrame(rows)


def test_stats_sparse_day():
    cfg = load_config()
    geom = load_geometry_cached(cfg)
    # one paint group only (like 2024-03-02 partial coverage in parquet)
    pg = int(next(iter(geom.pg_by_shp.values())))
    day = _synthetic_day(geom, [pg], [12.5])
    stats = compute_day_manifest_stats(day, geom)
    assert stats["n_districts_with_data"] >= 1
    assert stats["area_weighted_mean_mm"] == stats["area_weighted_mean_mm"]  # finite
    assert not np.isnan(stats["area_weighted_mean_mm"])


def test_stats_dense_day_weighted_mean():
    cfg = load_config()
    geom = load_geometry_cached(cfg)
    pgs = list({int(v) for v in list(geom.pg_by_shp.values())[:40]})
    mms = [float(i) for i in range(len(pgs))]
    day = _synthetic_day(geom, pgs, mms)
    stats = compute_day_manifest_stats(day, geom)
    vals = pd.Series({sid: mms[i] for i, sid in enumerate(list(geom.pg_by_shp.keys())[: len(pgs)]) if geom.pg_by_shp.get(sid) in pgs})
    # reference: align by shp from day paint path
    from rainfall.render_daily import _day_paint

    dp = _day_paint(geom, day)
    v = pd.Series(dp.shp_mm)
    w = pd.Series({sid: geom.area_by_shp.get(sid, 0) for sid in dp.shp_mm}).reindex(v.index).fillna(0)
    ref = float(np.average(v, weights=w))
    assert abs(stats["area_weighted_mean_mm"] - ref) < 1e-6
    assert stats["n_districts_with_data"] == len(dp.shp_mm)
