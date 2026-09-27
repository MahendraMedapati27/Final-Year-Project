"""P1b.5 JJAS national sanity vs IMD reference."""



from __future__ import annotations



import json



import numpy as np

import pandas as pd

import pyarrow.parquet as pq



from rainfall.config import resolve_path





def _india_area_km2() -> float:

    en = pd.read_parquet(

        resolve_path("data/processed/rainfall_enriched.parquet"),

        columns=["district_uid", "area_km2"],

    )

    one = en.drop_duplicates("district_uid").dropna(subset=["area_km2"])

    return float(one["area_km2"].sum())





def _national_daily_from_enriched() -> pd.DataFrame:

    from rainfall.aggregates import state_national_daily



    en_path = resolve_path("data/processed/rainfall_enriched.parquet")

    schema = pq.read_schema(en_path).names

    cols = ["date", "daily_actual_mm", "daily_actual_mm_map", "daily_normal_mm", "area_km2", "state_std"]

    cols = [c for c in cols if c in schema]

    en = pd.read_parquet(en_path, columns=cols)

    _, nat = state_national_daily(en)

    nat["date"] = pd.to_datetime(nat["date"])

    return nat





def run_jjas_sanity(use_map: bool = True) -> pd.DataFrame:

    """JJAS seasonal totals = sum of daily area-weighted national depth (mm)."""

    nat = _national_daily_from_enriched()

    area_km2 = _india_area_km2()

    nat["daily_actual_mm"] = nat["sum_actual_w"] / area_km2

    nat["daily_normal_mm"] = nat["sum_normal_w"] / area_km2

    jjas = nat[nat["date"].dt.month.isin([6, 7, 8, 9])].copy()



    rows = []

    for y in range(2021, 2026):

        cal = pd.date_range(f"{y}-06-01", f"{y}-09-30", freq="D")

        expected = len(cal)

        sub = jjas[jjas["date"].dt.year == y]

        present = set(sub["date"].dt.normalize())

        miss = sum(1 for d in cal if d not in present)

        jjas_act = float(sub["daily_actual_mm"].sum())

        jjas_norm = float(sub["daily_normal_mm"].sum())

        ratio = jjas_act / jjas_norm if jjas_norm else np.nan

        incomplete = miss > 0

        row: dict = {

            "year": y,

            "jjas_actual_mm_area_weighted": jjas_act,

            "jjas_normal_mm_area_weighted": jjas_norm,

            "actual_over_normal": float(ratio),

            "missing_jjas_days_in_data": int(miss),

            "incomplete_flag": bool(incomplete),

        }

        if incomplete and len(sub):

            both = sub.dropna(subset=["daily_actual_mm", "daily_normal_mm"])

            row["jjas_actual_present_days_only"] = float(both["daily_actual_mm"].sum())

            row["jjas_normal_present_days_only"] = float(both["daily_normal_mm"].sum())

            if both["daily_normal_mm"].sum():

                row["actual_over_normal_present_only"] = float(

                    both["daily_actual_mm"].sum() / both["daily_normal_mm"].sum()

                )

        rows.append(row)

    rep = pd.DataFrame(rows)

    rep.to_csv(resolve_path("outputs/tables/jjas_national_sanity.csv"), index=False)

    ref = 868.6

    payload = {

        "imd_reference_jjas_normal_mm": ref,

        "india_area_km2": area_km2,

        "rows": rep.to_dict(orient="records"),

        "max_normal_pct_diff_from_868.6": float((rep["jjas_normal_mm_area_weighted"] - ref).abs().max() / ref * 100),

    }

    resolve_path("outputs/checkpoints/p1b_jjas.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return rep

