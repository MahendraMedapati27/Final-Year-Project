"""No-data district reporting (P1b / trial captions)."""

from __future__ import annotations

import pandas as pd

from rainfall.config import resolve_path


def no_data_by_year() -> pd.DataFrame:
    en = pd.read_parquet(
        resolve_path("data/processed/rainfall_enriched.parquet"),
        columns=["date", "district_uid", "state_std", "district_std", "daily_actual_mm_map", "area_km2"],
    )
    en["date"] = pd.to_datetime(en["date"])
    en["year"] = en["date"].dt.year
    ac = "daily_actual_mm_map"
    rows = []
    for y, g in en.groupby("year", observed=True):
        area = g.drop_duplicates("district_uid")[["district_uid", "area_km2"]]["area_km2"].sum()
        nd = g[g[ac].isna()]
        nd_area = nd.drop_duplicates("district_uid")["area_km2"].sum()
        rows.append(
            {
                "year": int(y),
                "n_district_days_no_data": len(nd),
                "n_unique_districts_any_nan": nd["district_uid"].nunique(),
                "pct_area_no_data": float(nd_area / area * 100) if area else 0,
            }
        )
    return pd.DataFrame(rows).sort_values("year")


def top_districts_by_nan_days(n: int = 10) -> pd.DataFrame:
    en = pd.read_parquet(
        resolve_path("data/processed/rainfall_enriched.parquet"),
        columns=["date", "state_std", "district_std", "daily_actual_mm_map"],
    )
    en["date"] = pd.to_datetime(en["date"])
    nd = en[en["daily_actual_mm_map"].isna()]
    top = (
        nd.groupby(["state_std", "district_std"], observed=True)
        .size()
        .reset_index(name="n_nan_days")
        .sort_values("n_nan_days", ascending=False)
        .head(n)
    )
    return top


def no_data_districts_on_date(date: str) -> pd.DataFrame:
    d = pd.Timestamp(date)
    en = pd.read_parquet(
        resolve_path("data/processed/rainfall_enriched.parquet"),
        columns=["date", "state_std", "district_std", "daily_actual_mm_map", "area_km2"],
        filters=[("date", "=", d)],
    )
    return en[en["daily_actual_mm_map"].isna()].sort_values(["state_std", "district_std"])
