"""Independent stats-box numbers from enriched parquet + render geometry (no Matplotlib)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from rainfall.classes import daily_intensity_class
from rainfall.render_daily import _day_paint as build_day_paint
from rainfall.render_geom_cache import RenderGeometry


def _display_name(s: str) -> str:
    if not isinstance(s, str):
        return "?"
    return s.strip() or "?"


def compute_day_manifest_stats(day: pd.DataFrame, geom: RenderGeometry, *, mm_col: str = "daily_actual_mm_map") -> dict:
    """Match render_engine.FrozenRenderer metadata fields."""
    dp = build_day_paint(geom, day, mm_col=mm_col)
    meta: dict = {
        "n_districts_with_data": len(dp.shp_mm),
        "n_no_data": sum(1 for v in dp.shp_class.values() if v < 0),
        "n_parent_value": dp.n_parent,
        "n_excluded_suspect": dp.n_excluded_suspect,
        "n_heavy": int(sum(1 for v in dp.shp_mm.values() if v >= 64.5)),
    }
    if dp.shp_mm:
        vals = pd.Series(dp.shp_mm)
        w = pd.Series({sid: geom.area_by_shp.get(sid, 0) for sid in dp.shp_mm}).reindex(vals.index).fillna(0)
        if w.sum() > 0:
            meta["area_weighted_mean_mm"] = float(np.average(vals, weights=w))
        else:
            meta["area_weighted_mean_mm"] = float(vals.mean())
        meta["min_mm"] = float(vals.min())
        meta["max_mm"] = float(vals.max())
        sid_max = int(vals.idxmax())
        grow = geom.gdf[geom.gdf["shp_id"] == sid_max]
        if len(grow):
            meta["wettest_district"] = f"{grow['district_name'].iloc[0]}, {grow['state_name'].iloc[0]}"
        else:
            pg = geom.pg_by_shp.get(sid_max, -1)
            row = day[day["paint_group_uid"] == pg]
            if len(row):
                st = _display_name(row["state_std"].iloc[0] if "state_std" in row.columns else "?")
                dist = _display_name(row["district_std"].iloc[0] if "district_std" in row.columns else "?")
                meta["wettest_district"] = f"{dist}, {st}"
            else:
                meta["wettest_district"] = "?"
        meta["wettest_mm"] = float(vals.max())
    else:
        meta["area_weighted_mean_mm"] = float("nan")
        meta["min_mm"] = float("nan")
        meta["max_mm"] = float("nan")
        meta["wettest_district"] = ""
        meta["wettest_mm"] = float("nan")
    return meta
