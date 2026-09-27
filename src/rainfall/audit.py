"""Stage 1: data audit report and CSV exports."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from rainfall.config import load_config, project_root, resolve_path
from rainfall.io import ingest_command, load_parquet, map_raw_columns, read_raw_header, raw_csv_path

logger = logging.getLogger(__name__)

IMD_DEPARTURE_BINS = [
    ("LE", 60, np.inf),
    ("E", 20, 59.999),
    ("N", -19, 19),
    ("D", -59, -20),
    ("LD", -99, -60),
    ("NR", -100, -100),
]


def _null_counts(df: pd.DataFrame) -> pd.Series:
    return df.isna().sum()


def _calendar_analysis(df: pd.DataFrame) -> dict[str, Any]:
    dates = pd.to_datetime(df["date"]).dropna().dt.normalize().unique()
    dates = np.sort(dates)
    if len(dates) == 0:
        return {"error": "no dates"}
    full = pd.date_range(dates.min(), dates.max(), freq="D")
    missing = full.difference(pd.DatetimeIndex(dates))
    gaps = []
    if len(missing):
        miss_sorted = missing.sort_values()
        run_start = miss_sorted[0]
        prev = miss_sorted[0]
        for d in miss_sorted[1:]:
            if (d - prev).days > 1:
                gaps.append({"start": str(run_start.date()), "end": str(prev.date()), "days": (prev - run_start).days + 1})
                run_start = d
            prev = d
        gaps.append({"start": str(run_start.date()), "end": str(prev.date()), "days": (prev - run_start).days + 1})

    rows_per_date = df.groupby("date", observed=True).size()
    dist_per_date = df.groupby("date", observed=True)["district"].nunique()

    return {
        "first_date": str(pd.Timestamp(dates.min()).date()),
        "last_date": str(pd.Timestamp(dates.max()).date()),
        "n_unique_dates": int(len(dates)),
        "n_missing_calendar_days": int(len(missing)),
        "missing_gap_runs": gaps[:50],
        "rows_per_date": rows_per_date,
        "districts_per_date": dist_per_date,
    }


def _district_master(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["state", "district"], observed=True)
    master = g.agg(
        first_date=("date", "min"),
        last_date=("date", "max"),
        n_days=("date", "nunique"),
        n_obj_ids=("obj_id", lambda s: s.dropna().nunique()),
        n_null_actual=("daily_actual_mm", lambda s: s.isna().sum()),
    ).reset_index()
    return master


def _duplicate_groups(df: pd.DataFrame) -> pd.DataFrame:
    key = ["state", "district", "date"]
    dup_mask = df.duplicated(subset=key, keep=False)
    dups = df.loc[dup_mask].sort_values(key)
    return dups


def _value_qc(df: pd.DataFrame, extreme_mm: float) -> dict[str, Any]:
    actual = df["daily_actual_mm"]
    normal = df["daily_normal_mm"]
    dep = df["daily_departure_pct_provided"]
    neg_actual = (actual < 0).sum()
    neg_monthly = (df["monthly_actual_mm_provided"] < 0).sum()
    zeros = (actual == 0).sum()
    extreme = (actual > extreme_mm).sum()
    top20 = (
        df.nlargest(20, "daily_actual_mm", keep="all")[["state", "district", "date", "daily_actual_mm"]]
        .astype({"date": str})
        .to_dict("records")
    )
    stats = {
        "daily_actual_min": float(actual.min(skipna=True)),
        "daily_actual_max": float(actual.max(skipna=True)),
        "daily_actual_mean": float(actual.mean(skipna=True)),
        "daily_actual_median": float(actual.median(skipna=True)),
        "daily_actual_p99": float(actual.quantile(0.99)),
        "daily_actual_p999": float(actual.quantile(0.999)),
        "daily_normal_min": float(normal.min(skipna=True)),
        "daily_normal_max": float(normal.max(skipna=True)),
        "daily_normal_mean": float(normal.mean(skipna=True)),
        "daily_normal_median": float(normal.median(skipna=True)),
        "departure_min": float(dep.min(skipna=True)),
        "departure_max": float(dep.max(skipna=True)),
        "departure_mean": float(dep.mean(skipna=True)),
        "departure_median": float(dep.median(skipna=True)),
        "cumulative_actual_max": float(df["cumulative_actual_mm_provided"].max(skipna=True)),
        "cumulative_actual_median": float(df["cumulative_actual_mm_provided"].median(skipna=True)),
        "monthly_actual_min": float(df["monthly_actual_mm_provided"].min(skipna=True)),
        "monthly_actual_max": float(df["monthly_actual_mm_provided"].max(skipna=True)),
        "n_negative_daily_actual": int(neg_actual),
        "n_negative_monthly_actual": int(neg_monthly),
        "n_zero_daily_actual": int(zeros),
        "n_extreme_daily_actual": int(extreme),
        "top20_daily_actual": top20,
    }
    return stats


def _recompute_departure(actual: pd.Series, normal: pd.Series, guard: float) -> pd.Series:
    out = (actual - normal) / normal * 100.0
    out = out.where(normal >= guard)
    return out


def _departure_agreement(df: pd.DataFrame, guard: float) -> pd.DataFrame:
    rec = _recompute_departure(df["daily_actual_mm"], df["daily_normal_mm"], guard)
    mask = rec.notna() & df["daily_departure_pct_provided"].notna()
    diff = (rec[mask] - df.loc[mask, "daily_departure_pct_provided"]).abs()
    return pd.Series(
        {
            "n_comparable": int(mask.sum()),
            "median_abs_diff_pp": float(diff.median()) if len(diff) else np.nan,
            "mean_abs_diff_pp": float(diff.mean()) if len(diff) else np.nan,
            "pct_within_1pp": float((diff <= 1.0).mean() * 100) if len(diff) else np.nan,
        }
    )


def _category_from_departure(pct: float) -> str | None:
    if pd.isna(pct):
        return None
    if pct >= 60:
        return "LE"
    if pct >= 20:
        return "E"
    if pct >= -19:
        return "N"
    if pct >= -59:
        return "D"
    if pct >= -99:
        return "LD"
    if pct == -100:
        return "NR"
    return "ND"


def _category_agreement(df: pd.DataFrame, guard: float) -> pd.DataFrame:
    rec = _recompute_departure(df["daily_actual_mm"], df["daily_normal_mm"], guard)
    recomputed = rec.apply(_category_from_departure)
    provided = df["daily_category_provided"].astype(str)
    valid = recomputed.notna() & provided.notna() & (provided != "nan")
    cross = pd.crosstab(provided[valid], recomputed[valid], dropna=False)
    agree_rate = (provided[valid] == recomputed[valid]).mean() if valid.any() else np.nan
    return cross, float(agree_rate) if valid.any() else np.nan


def _weekly_vs_daily(df: pd.DataFrame) -> pd.DataFrame:
    eq = pd.Series(
        np.isclose(
            df["weekly_actual_mm_provided"].astype(float),
            df["daily_actual_mm"].astype(float),
            rtol=0,
            atol=1e-4,
            equal_nan=False,
        ),
        index=df.index,
    )
    tmp = df.assign(_eq=eq)
    by_date = tmp.groupby("date", observed=True).agg(n=("date", "size"), pct_weekly_eq_daily=("_eq", "mean"))
    by_date["pct_weekly_eq_daily"] *= 100.0
    return by_date


def _normal_doy_stability(df: pd.DataFrame) -> dict[str, Any]:
    df = df.copy()
    df["doy"] = pd.to_datetime(df["date"]).dt.dayofyear
    g = df.groupby(["state", "district", "doy"], observed=True)["daily_normal_mm"]
    nunique = g.nunique()
    unstable = (nunique > 1).sum()
    total = len(nunique)
    return {"groups": int(total), "groups_multiple_normals": int(unstable), "pct_unstable": 100.0 * unstable / max(total, 1)}


def _cumulative_consistency(df: pd.DataFrame, tol_mm: float = 1.0) -> dict[str, Any]:
    """Check cumulative actual vs sum of daily since cum_start (sample on subset)."""
    df = df.copy()
    df["cum_start"] = pd.to_datetime(df["cumulative_date_raw"], errors="coerce")
    valid = df["cum_start"].notna() & df["date"].notna()
    sub = df.loc[valid].copy()
    if sub.empty:
        return {"skipped": True}
    # Limit compute: group and compare last row cumulative vs sum
    results = []
    for (st, dist, cstart), g in sub.groupby(["state", "district", "cum_start"], observed=True):
        g = g.sort_values("date")
        daily_sum = g["daily_actual_mm"].sum(skipna=True)
        last_cum = g["cumulative_actual_mm_provided"].iloc[-1]
        if pd.notna(last_cum) and pd.notna(daily_sum):
            results.append(abs(float(last_cum) - float(daily_sum)) <= tol_mm)
    if not results:
        return {"n_checks": 0}
    arr = np.array(results)
    return {"n_checks": int(len(arr)), "pass_rate_pct": float(arr.mean() * 100)}


def _monthly_consistency(df: pd.DataFrame, tol_mm: float = 2.0) -> dict[str, Any]:
    df = df.copy()
    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M")
    results = []
    for (st, dist, month), g in df.groupby(["state", "district", "month"], observed=True):
        g = g.sort_values("date")
        mtd_sum = g["daily_actual_mm"].sum(skipna=True)
        last_m = g["monthly_actual_mm_provided"].iloc[-1]
        if pd.notna(last_m) and pd.notna(mtd_sum):
            results.append(abs(float(last_m) - float(mtd_sum)) <= tol_mm)
    if not results:
        return {"n_checks": 0}
    arr = np.array(results)
    return {"n_checks": int(len(arr)), "pass_rate_pct": float(arr.mean() * 100)}


def _portal_compare(stats: dict[str, Any], nulls: pd.Series, cfg: dict[str, Any]) -> pd.DataFrame:
    audit_cfg = cfg.get("audit", {})
    rows = [
        ("daily_actual_min", stats["daily_actual_min"], audit_cfg.get("portal_daily_actual_min"), "min"),
        ("daily_actual_max", stats["daily_actual_max"], audit_cfg.get("portal_daily_actual_max"), "max"),
        ("daily_actual_mean", stats["daily_actual_mean"], audit_cfg.get("portal_daily_actual_mean"), "mean"),
        ("daily_actual_median", stats["daily_actual_median"], audit_cfg.get("portal_daily_actual_median"), "median"),
        ("daily_normal_max", stats["daily_normal_max"], audit_cfg.get("portal_daily_normal_max"), "max"),
        ("daily_normal_mean", stats["daily_normal_mean"], audit_cfg.get("portal_daily_normal_mean"), "mean"),
        ("daily_normal_median", stats["daily_normal_median"], audit_cfg.get("portal_daily_normal_median"), "median"),
        ("departure_min", stats["departure_min"], audit_cfg.get("portal_daily_departure_min"), "min"),
        ("departure_max", stats["departure_max"], audit_cfg.get("portal_daily_departure_max"), "max"),
        ("departure_mean", stats["departure_mean"], audit_cfg.get("portal_daily_departure_mean"), "mean"),
        ("departure_median", stats["departure_median"], audit_cfg.get("portal_daily_departure_median"), "median"),
        ("cumulative_actual_max", stats["cumulative_actual_max"], audit_cfg.get("portal_cumulative_actual_max"), "max"),
        ("cumulative_actual_median", stats["cumulative_actual_median"], audit_cfg.get("portal_cumulative_actual_median"), "median"),
        ("monthly_actual_min", stats["monthly_actual_min"], audit_cfg.get("portal_monthly_actual_min"), "min"),
        ("monthly_actual_max", stats["monthly_actual_max"], audit_cfg.get("portal_monthly_actual_max"), "max"),
        ("obj_id_null", int(nulls.get("obj_id", 0)), audit_cfg.get("portal_obj_id_null"), "null_count"),
        ("weekly_date_null", int(nulls.get("weekly_date_raw", 0)), audit_cfg.get("portal_weekly_date_null"), "null_count"),
        ("weekly_category_null", int(nulls.get("weekly_category_provided", 0)), audit_cfg.get("portal_weekly_category_null"), "null_count"),
        ("cumulative_date_null", int(nulls.get("cumulative_date_raw", 0)), audit_cfg.get("portal_cumulative_date_null"), "null_count"),
        ("cumulative_category_null", int(nulls.get("cumulative_category_provided", 0)), audit_cfg.get("portal_cumulative_category_null"), "null_count"),
    ]
    out = pd.DataFrame(rows, columns=["metric", "computed", "portal", "kind"])
    out["match"] = np.isclose(
        out["computed"].astype(float),
        out["portal"].astype(float),
        rtol=0.02,
        atol=0.05,
        equal_nan=False,
    ) | (out["metric"].str.contains("null") & (out["computed"] == out["portal"]))
    return out


def _write_figures(cal: dict[str, Any], out_fig: Path) -> None:
    out_fig.mkdir(parents=True, exist_ok=True)
    if "rows_per_date" in cal and len(cal["rows_per_date"]):
        fig, ax = plt.subplots(figsize=(10, 4))
        cal["rows_per_date"].plot(ax=ax, lw=0.8)
        ax.set_title("Rows per date")
        ax.set_xlabel("Date")
        ax.set_ylabel("Row count")
        fig.tight_layout()
        fig.savefig(out_fig / "audit_rows_per_date.png", dpi=120)
        plt.close(fig)
    if "districts_per_date" in cal and len(cal["districts_per_date"]):
        fig, ax = plt.subplots(figsize=(10, 4))
        cal["districts_per_date"].plot(ax=ax, lw=0.8, color="darkgreen")
        ax.set_title("Unique districts per date")
        ax.set_xlabel("Date")
        ax.set_ylabel("District count")
        fig.tight_layout()
        fig.savefig(out_fig / "audit_districts_per_date.png", dpi=120)
        plt.close(fig)


def run_audit(sample: bool) -> Path:
    cfg = load_config()
    root = project_root()
    ingest_command(sample=sample, force=False)
    df = load_parquet(sample=sample)

    reports_dir = resolve_path(cfg["outputs"]["reports"])
    tables_dir = resolve_path(cfg["outputs"]["tables"])
    figures_dir = resolve_path(cfg["outputs"]["figures"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    nulls = _null_counts(df)
    cal = _calendar_analysis(df)
    master = _district_master(df)
    dups = _duplicate_groups(df)
    extreme_mm = float(cfg["cleaning"]["extreme_mm"])
    stats = _value_qc(df, extreme_mm)
    guard = float(cfg["cleaning"]["min_normal_mm_daily"])
    dep_agree = _departure_agreement(df, guard)
    cat_cross, cat_agree = _category_agreement(df, guard)
    weekly_by_date = _weekly_vs_daily(df)
    doy_stab = _normal_doy_stability(df)
    cum_check = _cumulative_consistency(df)
    mon_check = _monthly_consistency(df)
    portal = _portal_compare(stats, nulls, cfg)

    tag = "sample" if sample else "full"
    master.to_csv(tables_dir / f"district_master_{tag}.csv", index=False)
    portal.to_csv(tables_dir / f"portal_comparison_{tag}.csv", index=False)
    weekly_by_date.to_csv(tables_dir / f"weekly_vs_daily_by_date_{tag}.csv")
    pd.DataFrame([dep_agree]).to_csv(tables_dir / f"departure_recompute_agreement_{tag}.csv", index=False)
    cat_cross.to_csv(tables_dir / f"category_crosstab_{tag}.csv")
    if len(dups):
        dups.to_csv(tables_dir / f"duplicate_key_rows_{tag}.csv", index=False)

    cal_plot = {k: cal[k] for k in ("rows_per_date", "districts_per_date") if k in cal}
    _write_figures(cal_plot, figures_dir)

    mem_mb = df.memory_usage(deep=True).sum() / 1e6
    lines = [
        f"# Data audit ({tag})",
        "",
        f"- Rows: **{len(df):,}** | Columns: **{len(df.columns)}** | Memory (deep): **{mem_mb:.1f} MB**",
        f"- Date range: {cal.get('first_date')} → {cal.get('last_date')} ({cal.get('n_unique_dates')} unique dates)",
        f"- Missing calendar days in span: **{cal.get('n_missing_calendar_days')}**",
        "",
        "## Portal metadata comparison",
        portal.to_markdown(index=False),
        "",
        "## Null counts (selected)",
        nulls.head(25).to_markdown(),
        "",
        "## Duplicates on (state, district, date)",
        f"- Duplicate rows: **{len(dups)}** ({dups.groupby(['state', 'district', 'date'], observed=True).ngroups if len(dups) else 0} groups)",
        "",
        "## Value QC summary",
        f"- Negative daily actual: {stats['n_negative_daily_actual']}",
        f"- Zero daily actual: {stats['n_zero_daily_actual']}",
        f"- Extreme (>{extreme_mm} mm): {stats['n_extreme_daily_actual']}",
        f"- Daily actual max: {stats['daily_actual_max']} mm",
        "",
        "## Departure recompute (normal >= {guard} mm)",
        dep_agree.to_markdown(),
        "",
        f"## Category agreement (recomputed vs provided): **{cat_agree * 100:.2f}%**",
        "",
        "## Weekly actual vs daily (by date, % equal)",
        weekly_by_date.describe().to_markdown() if len(weekly_by_date) else "_n/a_",
        "",
        "## Consistency checks",
        f"- Normal stability (same DOY multiple values): {doy_stab}",
        f"- Cumulative vs daily sum: {cum_check}",
        f"- Monthly vs daily sum: {mon_check}",
        "",
        "## Known issues register",
        "1. Duplicate keys resolved in clean stage (prefer non-null actual; richer obj_id history).",
        "2. Departure % unreliable when normal ≈ 0; recompute with guard.",
        "3. Categories recomputed from guarded departure; provided kept.",
        "4. Weekly columns often equal daily — not rolling 7-day; compute own rolling sums.",
        "5. Obj_Id not a shapefile key; missing ~72% in full data.",
        "6. District/state name variants require crosswalk + aliases.",
        "",
    ]
    report_path = reports_dir / ("data_audit_sample.md" if sample else "data_audit_full.md")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    if not sample:
        (reports_dir / "data_audit.md").write_text("\n".join(lines), encoding="utf-8")

    logger.info("Audit report: %s", report_path)
    print("\n=== AUDIT SUMMARY (%s) ===" % tag)
    print(f"Rows: {len(df):,}")
    print(portal.to_string(index=False))
    print(f"\nDuplicate rows: {len(dups)}")
    print(f"Missing calendar days: {cal.get('n_missing_calendar_days')}")
    print(f"Category agreement: {cat_agree * 100:.2f}%")
    print(f"Report: {report_path}")
    return report_path


def verify_header(csv_path: Path) -> None:
    cols = read_raw_header(csv_path)
    map_raw_columns(cols)
    print(f"Header OK: {len(cols)} columns")
    for i, c in enumerate(cols):
        print(f"  [{i}] {c[:80]}{'...' if len(c) > 80 else ''}")
