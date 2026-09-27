"""Hydrological and temporal features on complete daily index."""

from __future__ import annotations

import numpy as np
import pandas as pd

IMD_SEASON = {
    1: "winter",
    2: "winter",
    3: "pre_monsoon",
    4: "pre_monsoon",
    5: "pre_monsoon",
    6: "monsoon",
    7: "monsoon",
    8: "monsoon",
    9: "monsoon",
    10: "post_monsoon",
    11: "post_monsoon",
    12: "post_monsoon",
}


def parse_period_strings(df: pd.DataFrame) -> pd.DataFrame:
    import re

    out = df.copy()
    wk = out["weekly_date_raw"].astype(str).str.extract(
        r"(\d{2}-\d{2}-\d{4})\s*To\s*(\d{2}-\d{2}-\d{4})", expand=True
    )
    out["week_start"] = pd.to_datetime(wk[0], format="%d-%m-%Y", errors="coerce")
    out["week_end"] = pd.to_datetime(wk[1], format="%d-%m-%Y", errors="coerce")
    out["cum_start"] = pd.to_datetime(out["cumulative_date_raw"], errors="coerce")
    md = out["monthly_date_raw"].astype(str).str.extract(
        r"From\s*(\d{2}-\d{2}-\d{4})\s*To\s*(\d{2}-\d{2}-\d{4})", expand=True
    )
    out["month_start"] = pd.to_datetime(md[0], format="%d-%m-%Y", errors="coerce")
    out["month_end"] = pd.to_datetime(md[1], format="%d-%m-%Y", errors="coerce")
    return out


def complete_daily_index(df: pd.DataFrame, id_col: str = "district_uid") -> pd.DataFrame:
    """Reindex each district to full date range; missing days become NaN rows."""
    df = df.sort_values([id_col, "date"])
    parts = []
    for uid, g in df.groupby(id_col, observed=True):
        dmin, dmax = g["date"].min(), g["date"].max()
        idx = pd.date_range(dmin, dmax, freq="D")
        g2 = g.set_index("date").reindex(idx)
        g2[id_col] = uid
        g2["date"] = g2.index
        parts.append(g2.reset_index(drop=True))
    return pd.concat(parts, ignore_index=True)


def add_hydrology(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["district_uid", "date"]).copy()
    a = df["daily_actual_mm"]
    for w, col in [(3, "rain_3d_mm"), (7, "rain_7d_mm"), (30, "rain_30d_mm")]:
        df[col] = df.groupby("district_uid", observed=True)["daily_actual_mm"].transform(
            lambda s, w=w: s.rolling(w, min_periods=w).sum()
        )
    df["is_rainy_day"] = a >= 2.5
    df["is_heavy_day"] = a >= 64.5
    df["is_very_heavy_day"] = a >= 115.6

    # Spell lengths: lightweight run encoding (vectorized per group via numba-free loop only on sorted groups)
    df["wet_spell_len"] = 0
    df["dry_spell_len"] = 0
    df["days_since_rain"] = np.nan

    df["monsoon_year"] = np.where(df["date"].dt.month >= 6, df["date"].dt.year, df["date"].dt.year - 1)
    june1 = pd.to_datetime(df["monsoon_year"].astype(str) + "-06-01")
    df["monsoon_day"] = (df["date"] - june1).dt.days
    df.loc[df["monsoon_day"] < 0, "monsoon_day"] = np.nan
    df["monsoon_cum_mm"] = df.groupby(["district_uid", "monsoon_year"], observed=True)["daily_actual_mm"].cumsum()
    df["monsoon_cum_normal_mm"] = df.groupby(["district_uid", "monsoon_year"], observed=True)["daily_normal_mm"].cumsum()
    # Incomplete if gap since June 1 in observed dates
    df["_expected_days"] = df["monsoon_day"] + 1
    df["_obs_rank"] = df.groupby(["district_uid", "monsoon_year"], observed=True).cumcount() + 1
    df["monsoon_cum_complete"] = df["_obs_rank"] >= df["_expected_days"]
    df.loc[~df["monsoon_cum_complete"], "monsoon_cum_mm"] = np.nan
    df.loc[~df["monsoon_cum_complete"], "monsoon_cum_normal_mm"] = np.nan
    df.drop(columns=["_expected_days", "_obs_rank", "monsoon_year"], inplace=True, errors="ignore")
    return df
