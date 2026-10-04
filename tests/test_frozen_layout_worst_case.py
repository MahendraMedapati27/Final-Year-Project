"""Data-driven worst-case layout: UI must not overlap district pixels."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from rainfall.config import load_config, resolve_path
from rainfall.render_daily import DailyMapRenderer
from rainfall.render_geom_cache import load_geometry_cached
from rainfall.render_layout import ui_overlaps_land


def _worst_dates() -> list[str]:
    p = resolve_path("outputs/checkpoints/worst_layout_dates.json")
    if not p.exists():
        pytest.skip("Run scripts/verify/find_worst_layout_dates.py first")
    data = json.loads(p.read_text(encoding="utf-8"))
    return data["test_dates"]


@pytest.mark.full
def test_worst_case_layout_no_land_overlap():
    dates = _worst_dates()
    cfg = load_config()
    geom = load_geometry_cached(cfg)
    cols = [
        "date",
        "paint_group_uid",
        "daily_actual_mm_map",
        "state_std",
        "district_std",
        "qc_isolated_extreme",
        "resolution",
    ]
    failures: list[str] = []
    for date_s in [d for d in dates if d]:
        r = DailyMapRenderer(cfg=cfg, geom=geom)
        d = pd.Timestamp(date_s)
        day = pd.read_parquet(resolve_path(cfg["paths"]["processed_enriched"]), filters=[("date", "=", d)], columns=cols)
        r.draw_date(d, day)
        bad = [k for k, v in ui_overlaps_land(r).items() if v]
        if bad:
            failures.append(f"{date_s}: {bad}")
    assert not failures, failures
