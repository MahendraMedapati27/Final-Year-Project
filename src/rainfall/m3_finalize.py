"""Post-merge exports: missing-day table, aggregates, data dictionary."""

from __future__ import annotations

import pandas as pd
import pyarrow.parquet as pq

from rainfall.aggregates import district_period_indices, state_national_daily
from rainfall.config import load_config, resolve_path


def export_missing_days(df: pd.DataFrame) -> None:
    all_dates = pd.date_range("2021-01-01", "2026-09-19", freq="D")
    present = set(pd.to_datetime(df["date"].unique()))
    missing = all_dates.difference(present)
    miss_df = pd.DataFrame({"date": missing})
    miss_df["year"] = miss_df["date"].dt.year
    miss_df["month"] = miss_df["date"].dt.month
    miss_by_month = miss_df.groupby(["year", "month"], observed=True).size().reset_index(name="n_missing")
    miss_by_month.to_csv(resolve_path("outputs/tables/missing_days_by_month.csv"), index=False)


def export_jjas_coverage(df: pd.DataFrame) -> pd.DataFrame:
    sub = df[df["date"].dt.month.isin([6, 7, 8, 9])].copy()
    sub["year"] = sub["date"].dt.year
    by = sub.groupby(["state_std", "district_std", "year"], observed=True).agg(
        n_days=("date", "count"),
        n_actual=("daily_actual_mm", lambda s: s.notna().sum()),
    )
    by["coverage"] = by["n_actual"] / by["n_days"]
    by = by.reset_index()
    by.to_csv(resolve_path("outputs/tables/jjas_coverage_by_district_year.csv"), index=False)
    yr = by.groupby("year", observed=True)["coverage"].median().reset_index(name="median_jjas_coverage")
    yr.to_csv(resolve_path("outputs/tables/jjas_coverage_median_by_year.csv"), index=False)
    return yr


def write_data_dictionary(path: str) -> None:
    schema = pq.read_schema(path)
    lines = ["# rainfall_enriched data dictionary\n", f"Source: `{path}`\n\n", "| column | type |\n", "|---|---|\n"]
    for name in schema.names:
        lines.append(f"| `{name}` | {schema.field(name).type} |\n")
    resolve_path("outputs/reports/data_dictionary.md").write_text("".join(lines), encoding="utf-8")


def run_finalize() -> None:
    cfg = load_config()
    path = resolve_path(cfg["paths"]["processed_enriched"])
    df = pd.read_parquet(path)
    export_missing_days(df)
    export_jjas_coverage(df)
    tables = resolve_path(cfg["outputs"]["tables"])
    st_daily, nat_daily = state_national_daily(df)
    st_daily.to_parquet(tables / "state_daily.parquet", index=False)
    nat_daily.to_parquet(tables / "national_daily.parquet", index=False)
    district_period_indices(df, "month").to_parquet(tables / "district_monthly.parquet", index=False)
    district_period_indices(df, "season").to_parquet(tables / "district_season.parquet", index=False)
    district_period_indices(df, "year").to_parquet(tables / "district_annual.parquet", index=False)
    write_data_dictionary(str(path))
