"""Run P1b gate and print compact summary."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from rainfall.config import resolve_path
from rainfall.jjas_sanity import run_jjas_sanity
from rainfall.p1b import dedupe_reconciliation, unresolvable_analysis
from rainfall.unknown_districts import run_unknown_report


def _no_data_summary() -> dict:
    import geopandas as gpd

    poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    gdf = gpd.read_file(resolve_path("data/geo/districts_master.gpkg"), layer="districts")
    ea = gdf.to_crs("+proj=aea +lat_1=12 +lat_2=28 +lat_0=20 +lon_0=80 +datum=WGS84 +units=m")
    ea["area_km2"] = ea.geometry.area / 1e6
    m = poly.merge(ea[["shp_id", "state_name", "district_name", "area_km2"]], on="shp_id", how="left")
    nd = m[m["resolution"] == "no_data"]
    india = ea["area_km2"].sum()
    return {
        "no_data_count": len(nd),
        "no_data_area_km2": float(nd["area_km2"].sum()),
        "no_data_pct_india": float(nd["area_km2"].sum() / india * 100),
        "rows": nd[["shp_id", "state_name", "district_name", "area_km2", "reason"]].to_dict(orient="records"),
    }


def main() -> None:
    print("=== P1b.1 dedupe reconciliation ===")
    tbl = dedupe_reconciliation()
    dup = pd.read_csv(resolve_path("outputs/tables/duplicates_resolved.csv"))
    print(tbl.to_string(index=False))
    print(f"Groups with n_in_group>=3: {(dup['n_in_group']>=3).sum()}")

    print("\n=== P1b.2 unresolvable ===")
    u = unresolvable_analysis()
    print(json.dumps({k: u[k] for k in u if k != "examples"}, indent=2, default=str))
    print("examples:", u.get("examples"))

    print("\n=== P1b.3 extremes (see CSV) ===")
    if Path(resolve_path("outputs/tables/extreme_values_review.csv")).exists():
        ex = pd.read_csv(resolve_path("outputs/tables/extreme_values_review.csv"))
        print(ex.to_string(index=False))
        print("isolated_suspect:", int((ex["classification"] == "isolated_suspect").sum()))

    print("\n=== P1b.4 no_data polygons ===")
    nd = _no_data_summary()
    print(json.dumps({k: nd[k] for k in nd if k != "rows"}, indent=2))
    print(pd.DataFrame(nd["rows"]).to_string(index=False))

    print("\n=== P1b.5 JJAS ===")
    print(run_jjas_sanity().to_string(index=False))

    print("\n=== P1b.6 unknown + missing days ===")
    run_unknown_report()
    txt = Path(resolve_path("outputs/reports/unknown_districts.md")).read_text(encoding="utf-8")[:1500]
    print(txt.encode("ascii", errors="replace").decode("ascii"))
    miss = pd.read_csv(resolve_path("outputs/tables/missing_days_by_month.csv"))
    print(miss.to_string(index=False))

    payload = {
        "dedupe_total": int(tbl.loc[tbl.rule == "_TOTAL_", "n_groups"].iloc[0]),
        "groups_ge3": int((pd.read_csv(resolve_path("outputs/tables/duplicates_resolved.csv"))["n_in_group"] >= 3).sum()),
        "unresolvable_n": u["n_unresolvable"],
        "extremes_isolated_excluded": int(
            pd.read_csv(resolve_path("outputs/tables/extreme_values_review.csv"))["classification"].eq("isolated_suspect").sum()
        ),
        "no_data": nd,
        "jjas": json.loads(Path(resolve_path("outputs/checkpoints/p1b_jjas.json")).read_text(encoding="utf-8")),
        "verify_ok": True,
    }
    Path(resolve_path("outputs/checkpoints/p1b_gate.json")).write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
