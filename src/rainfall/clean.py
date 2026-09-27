"""M3: dedupe, clean, enrich."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from rainfall.aggregates import district_period_indices, state_national_daily
from rainfall.classes import daily_intensity_class, departure_category, guarded_departure
from rainfall.config import load_config, resolve_path
from rainfall.features import IMD_SEASON, add_hydrology, parse_period_strings
from rainfall.io import load_parquet, write_stage_manifest
from rainfall.names import normalize_district, normalize_state

logger = logging.getLogger(__name__)

VALUE_COLS_FOR_TIE = [
    "daily_actual_mm",
    "daily_normal_mm",
    "weekly_actual_mm_provided",
    "cumulative_actual_mm_provided",
    "monthly_actual_mm_provided",
]


def _nonnull_count(row: pd.Series) -> int:
    return sum(pd.notna(row.get(c)) for c in VALUE_COLS_FOR_TIE if c in row.index)


def dedupe_dataframe(df: pd.DataFrame, primary_oid: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    oid_map = primary_oid.set_index(["state", "district"])["primary_obj_id"].to_dict()
    key = ["state", "district", "date"]
    logs: list[pd.DataFrame] = []
    kept_rows: list[pd.DataFrame] = []

    dup_mask = df.duplicated(subset=key, keep=False)
    singles = df[~dup_mask].copy()
    singles["qc_dup_resolved"] = False
    singles["qc_dup_conflict"] = False
    kept_rows.append(singles)

    for _, g in df[dup_mask].groupby(key, observed=True):
        g = g.copy()
        rule = "multi"
        pool = g[g["daily_actual_mm"].notna()]
        if len(pool) == 0:
            kept = g.iloc[0]
            dropped = g.iloc[1:]
            rule = "all_nan_first"
        elif len(pool) == 1:
            kept = pool.iloc[0]
            dropped = g.drop(kept.name)
            rule = "non_null_actual"
        else:
            g2 = pool
            st, dist = g2.iloc[0]["state"], g2.iloc[0]["district"]
            pref = oid_map.get((st, dist))
            if pref is not None and (g2["obj_id"] == pref).any():
                kept = g2[g2["obj_id"] == pref].iloc[0]
                rule = "preferred_obj_id"
            else:
                g2 = g2.copy()
                g2["_nn"] = g2.apply(_nonnull_count, axis=1)
                kept = g2.sort_values("_nn", ascending=False).iloc[0]
                rule = "most_nonnull_cols"
            dropped = g.drop(kept.name)

        kept = kept.copy()
        kept["qc_dup_resolved"] = True
        kept["qc_dup_conflict"] = False
        nonnull_vals = g["daily_actual_mm"].dropna()
        if len(nonnull_vals) > 1 and nonnull_vals.nunique() > 1:
            kept["daily_actual_mm"] = float(nonnull_vals.mean())
            kept["qc_dup_conflict"] = True
            rule = "mean_conflict"

        logs.append(_log_row(key, kept, dropped, rule, g))
        kept_rows.append(pd.DataFrame([kept]))

    out = pd.concat(kept_rows, ignore_index=True)
    log_df = pd.concat(logs, ignore_index=True) if logs else pd.DataFrame()
    return out, log_df


def _log_row(key, kept, dropped, rule, g):
    return pd.DataFrame(
        [
            {
                "state": kept["state"],
                "district": kept["district"],
                "date": kept["date"],
                "rule": rule,
                "kept_obj_id": kept.get("obj_id"),
                "dropped_obj_ids": dropped["obj_id"].tolist() if len(dropped) else [],
                "kept_actual": kept.get("daily_actual_mm"),
                "dropped_actuals": dropped["daily_actual_mm"].tolist() if len(dropped) else [],
                "n_in_group": len(g),
            }
        ]
    )


def relabel_unknown(df: pd.DataFrame, imd_map: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["qc_relabelled_unknown"] = False
    df["qc_placeholder_district"] = df["district"].astype(str).str.contains("Unknown Districts", case=False, na=False)
    unk = df["qc_placeholder_district"]
    # obj_id -> single imd district name -> match existing (state,district) in data
    for oid, sub in df[unk & df["obj_id"].notna()].groupby("obj_id"):
        oid = int(oid)
        imd_rows = imd_map[imd_map["obj_id"] == oid]
        if len(imd_rows) != 1:
            continue
        name = imd_rows.iloc[0]["district_name"]
        st = imd_rows.iloc[0]["state_name"]
        # find dataset district with same name in same state
        candidates = df[(df["state"] == st) & (df["district"] == name)]
        if len(candidates) == 0:
            continue
        df.loc[sub.index, "district"] = name
        df.loc[sub.index, "state"] = st
        df.loc[sub.index, "qc_relabelled_unknown"] = True
        df.loc[sub.index, "qc_placeholder_district"] = False
    return df


def run_clean(sample: bool = False) -> Path:
    cfg = load_config()
    df = load_parquet(sample=sample)
    n_before = len(df)

    primary_path = resolve_path("outputs/tables/district_primary_obj_id.csv")
    primary = pd.read_csv(primary_path) if primary_path.exists() else pd.DataFrame(columns=["state", "district", "primary_obj_id"])

    from rainfall.validate_crosswalk import load_imd_gist

    imd = load_imd_gist()
    df = relabel_unknown(df, imd)

    df, dup_log = dedupe_dataframe(df, primary)
    n_after = len(df)

    tables = resolve_path(cfg["outputs"]["tables"])
    tables.mkdir(parents=True, exist_ok=True)
    dup_log.to_csv(tables / "duplicates_resolved.csv", index=False)

    cw = pd.read_csv(resolve_path(cfg["paths"]["crosswalk"]))
    pg = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    uid_map = { (r["dataset_state"], r["dataset_district"]): (r["paint_group_uid"], r.get("shp_id"), r.get("match_method"), r.get("match_score"))
                for _, r in cw.iterrows()}

    df["state_std"] = df["state"].map(normalize_state)
    df["district_std"] = df.apply(lambda r: normalize_district(r["district"], r["state"]), axis=1)
    df["district_uid"] = df.groupby(["state_std", "district_std"], observed=True).ngroup().astype(np.int32) + 1

    for col, src in [
        ("paint_group_uid", 0),
        ("shp_id", 1),
        ("match_method", 2),
        ("match_score", 3),
    ]:
        df[col] = df.apply(lambda r, i=src: uid_map.get((r["state"], r["district"]), (np.nan,) * 4)[i], axis=1)

    df = parse_period_strings(df)
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["day"] = df["date"].dt.day
    df["doy"] = df["date"].dt.dayofyear
    df["iso_week"] = df["date"].dt.isocalendar().week.astype(int)
    df["season"] = df["month"].map(IMD_SEASON)
    df["is_monsoon"] = df["month"].isin([6, 7, 8, 9])

    guard_d = float(cfg["cleaning"]["min_normal_mm_daily"])
    df["daily_departure_pct"] = guarded_departure(df["daily_actual_mm"], df["daily_normal_mm"], guard_d)
    df["daily_anomaly_mm"] = df["daily_actual_mm"] - df["daily_normal_mm"]
    df["daily_departure_pct_provided"] = df.get("daily_departure_pct_provided")

    df["qc_negative_fixed"] = False
    mneg = df["daily_actual_mm"] < 0
    df.loc[mneg, "qc_negative_fixed"] = True
    df.loc[mneg, "daily_actual_mm"] = np.nan
    mnegm = df["monthly_actual_mm_provided"] < 0
    df.loc[mnegm, "monthly_actual_mm_provided"] = np.nan

    extreme = float(cfg["cleaning"]["extreme_mm"])
    df["qc_extreme_actual"] = df["daily_actual_mm"] > extreme
    df["qc_missing_actual"] = df["daily_actual_mm"].isna()
    df["qc_missing_normal"] = df["daily_normal_mm"].isna()
    df["qc_departure_undefined"] = df["daily_normal_mm"].lt(guard_d) | df["daily_normal_mm"].isna()
    df["qc_no_geometry"] = df["shp_id"].isna()

    labels, codes = daily_intensity_class(df["daily_actual_mm"])
    df["daily_intensity_class"] = labels
    df["daily_intensity_code"] = codes
    df["daily_departure_cat"] = departure_category(df["daily_departure_pct"])
    df["daily_departure_cat_provided"] = df["daily_category_provided"]
    df["daily_departure_cat_agrees"] = df["daily_departure_cat"] == df["daily_departure_cat_provided"]

    # area from paint group
    cw_area = cw.set_index("paint_group_uid")["area_km2_total"]
    df["area_km2"] = df["paint_group_uid"].map(cw_area)
    gpkg = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="districts")
    cent = gpkg.set_index("shp_id")[["centroid_lon", "centroid_lat"]]
    df["centroid_lon"] = df["shp_id"].map(cent["centroid_lon"])
    df["centroid_lat"] = df["shp_id"].map(cent["centroid_lat"])
    df["daily_volume_mcm"] = df["daily_actual_mm"] * df["area_km2"] / 1000.0

    df = add_hydrology(df)

    out = resolve_path(cfg["paths"]["processed_enriched"])
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, compression="zstd", index=False)
    df.head(50000).to_csv(str(out.with_suffix(".csv.gz")), compression="gzip", index=False)

    # Missing days table
    all_dates = pd.date_range(df["date"].min(), df["date"].max(), freq="D")
    present = set(df["date"].unique())
    missing = all_dates.difference(present)
    miss_df = pd.DataFrame({"date": missing})
    miss_df["year"] = miss_df["date"].dt.year
    miss_df["month"] = miss_df["date"].dt.month
    miss_by_month = miss_df.groupby(["year", "month"], observed=True).size().reset_index(name="n_missing")
    miss_by_month.to_csv(tables / "missing_days_by_month.csv", index=False)

    try:
        st_daily, nat_daily = state_national_daily(df)
        st_daily.to_parquet(tables / "state_daily.parquet", index=False)
        nat_daily.to_parquet(tables / "national_daily.parquet", index=False)
        district_period_indices(df, "month").to_parquet(tables / "district_monthly.parquet", index=False)
        district_period_indices(df, "season").to_parquet(tables / "district_season.parquet", index=False)
        district_period_indices(df, "year").to_parquet(tables / "district_annual.parquet", index=False)
    except Exception as exc:
        logger.warning("Aggregate tables skipped: %s", exc)

    conflicts = df.get("qc_dup_conflict", pd.Series(False, index=df.index)).sum()
    print(f"Rows before: {n_before:,} after: {n_after:,} dup groups logged: {len(dup_log):,} conflicts: {conflicts}")
    write_stage_manifest("clean", {"enriched": str(out)}, extra={"n_before": n_before, "n_after": n_after})
    return out
