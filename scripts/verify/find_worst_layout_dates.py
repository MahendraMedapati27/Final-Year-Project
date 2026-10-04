"""Find real worst-case dates for layout overlap tests."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from rainfall.config import load_config, resolve_path
from rainfall.render_daily import _display_name
from rainfall.render_geom_cache import load_geometry_cached


def main() -> None:
    en = pd.read_parquet(
        resolve_path("data/processed/rainfall_enriched.parquet"),
        columns=[
            "date",
            "paint_group_uid",
            "daily_actual_mm_map",
            "state_std",
            "district_std",
            "area_km2",
            "resolution",
            "qc_isolated_extreme",
        ],
    )
    en["date"] = pd.to_datetime(en["date"])
    ac = "daily_actual_mm_map"
    poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    total_area = en.drop_duplicates("paint_group_uid")["area_km2"].sum()

    best_legend = ("", -1, 0.0)
    best_wet = ("", "", 0)
    best_parent = ("", 0)
    best_excl = ("", 0)
    cfg = load_config()
    geom = load_geometry_cached(cfg)
    child_shp = {sid for sid, res in geom.resolution_by_shp.items() if str(res).startswith("child_of")}

    for d, g in en.groupby("date", observed=True):
        ds = str(d.date())
        mm = g[ac]
        n_data = int(mm.notna().sum())
        nd = int(mm.isna().sum())
        nd_pct = 100.0 * g.loc[mm.isna(), "area_km2"].sum() / total_area if total_area else 0
        legend_score = len(str(n_data)) * 1000 + len(f"{nd_pct:.1f}") + nd
        if legend_score > best_legend[1]:
            best_legend = (ds, legend_score, nd_pct)
        if mm.notna().any():
            idx = mm.idxmax()
            st = _display_name(g.loc[idx, "state_std"])
            dist = _display_name(g.loc[idx, "district_std"])
            wet_str = f"Wettest: {dist}, {st} ({float(mm.max()):.1f} mm)"
            if len(wet_str) > best_wet[2]:
                best_wet = (ds, wet_str, len(wet_str))
        pgs_with_data = set(g.loc[g[ac].notna(), "paint_group_uid"])
        n_parent = sum(
            1
            for sid in child_shp
            if geom.pg_by_shp.get(sid, -1) in pgs_with_data
        )
        if n_parent > best_parent[1]:
            best_parent = (ds, n_parent)
        n_ex = int(g["qc_isolated_extreme"].fillna(False).sum()) if "qc_isolated_extreme" in g.columns else 0
        if n_ex > best_excl[1]:
            best_excl = (ds, n_ex)

    dates = sorted({d for d in (best_legend[0], best_wet[0], best_parent[0], best_excl[0]) if d})
    out = {
        "widest_legend_date": best_legend[0],
        "widest_legend_nd_pct": float(best_legend[2]),
        "longest_wettest_date": best_wet[0],
        "longest_wettest_string": best_wet[1],
        "max_parent_date": best_parent[0],
        "max_parent_n": best_parent[1],
        "max_excluded_date": best_excl[0],
        "max_excluded_n": best_excl[1],
        "test_dates": dates,
    }
    p = resolve_path("outputs/checkpoints/worst_layout_dates.json")
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
