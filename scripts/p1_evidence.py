"""Print P1 gate evidence (schema, dedupe, spatial, homonyms)."""

from __future__ import annotations

import json

import pandas as pd

from rainfall.config import resolve_path
from rainfall.spatial_validate import run_spatial_validation
from rainfall.verify import run_verify


def main() -> None:
    v = run_verify()
    print("=== verify ===")
    print(json.dumps(v, indent=2))
    cl = pd.read_csv(resolve_path("outputs/tables/schema_checklist.csv"))
    print("\n=== schema checklist (missing only) ===")
    miss = cl[~cl["present"]]
    print(miss.to_string(index=False) if len(miss) else "all present")
    print("\n=== schema summary ===")
    print(cl.groupby("section")["present"].agg(["sum", "count"]))

    dup = pd.read_csv(resolve_path("outputs/tables/duplicates_resolved.csv"))
    print("\n=== dedupe methods ===")
    print(dup["rule"].value_counts().to_string())

    raw = pd.read_parquet(resolve_path("data/interim/raw_full.parquet"), columns=["state", "district", "date", "daily_actual_mm"])
    dup_keys = raw.groupby(["state", "district", "date"]).ngroups
    heavy_raw = raw[raw["daily_actual_mm"] > 500]
    print(f"\nRaw rows >500mm: {len(heavy_raw)}")
    en = pd.read_parquet(resolve_path("data/processed/rainfall_enriched.parquet"), columns=["daily_actual_mm", "state", "district", "date", "qc_dup_resolved"])
    heavy_en = en[en["daily_actual_mm"] > 500]
    print(f"Enriched rows >500mm: {len(heavy_en)}")

    spatial = run_spatial_validation()
    fails = spatial[~spatial["inside_state"]]
    print(f"\nSpatial failures: {len(fails)}")
    for name in ["Pratapgarh", "Bilaspur", "Hamirpur"]:
        sub = spatial[spatial["dataset_district"].str.contains(name, na=False)]
        print(f"\n--- {name} ---")
        print(sub[["dataset_state", "dataset_district", "shp_id", "centroid_lon", "centroid_lat", "inside_state"]].to_string(index=False))

    resolve_path("outputs/checkpoints/p1_gate.json").write_text(
        json.dumps({"verify": v, "spatial_failures": int(len(fails))}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
