"""State/national and district temporal aggregates (PROMPT 6.8)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from rainfall.classes import guarded_departure


def spatial_distribution_class(frac: float) -> str:
    if frac <= 0.25:
        return "Isolated"
    if frac <= 0.50:
        return "Scattered"
    if frac <= 0.75:
        return "Fairly Widespread"
    return "Widespread"


def _actual_col(df: pd.DataFrame) -> str:
    return "daily_actual_mm_map" if "daily_actual_mm_map" in df.columns else "daily_actual_mm"


def state_national_daily(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ac = _actual_col(df)
    d = df.dropna(subset=[ac, "area_km2"]).copy()
    d["w"] = d["area_km2"]
    g = d.groupby(["date", "state_std"], observed=True)
    state = g.apply(
        lambda x: pd.Series(
            {
                "actual_mm_wmean": np.average(x[ac], weights=x["w"]),
                "normal_mm_wmean": np.average(x["daily_normal_mm"], weights=x["w"]),
                "actual_sum": (x[ac] * x["w"]).sum() / x["w"].sum(),
                "normal_sum_num": (x["daily_normal_mm"] * x["w"]).sum(),
                "weight_sum": x["w"].sum(),
                "n_districts": len(x),
                "frac_rainy": (x[ac] >= 2.5).mean(),
                "frac_heavy": (x[ac] >= 64.5).mean(),
            }
        ),
        include_groups=False,
    ).reset_index()
    state["departure_pct"] = (state["actual_sum"] - state["normal_sum_num"] / state["weight_sum"] * state["weight_sum"]) / (
        state["normal_sum_num"] / state["weight_sum"] * state["weight_sum"]
    ) * 100
    # correct: dep from sums
    state["sum_actual_w"] = d.groupby(["date", "state_std"], observed=True).apply(
        lambda x: (x[ac] * x["area_km2"]).sum(), include_groups=False
    ).values
    state["sum_normal_w"] = d.groupby(["date", "state_std"], observed=True).apply(
        lambda x: (x["daily_normal_mm"] * x["area_km2"]).sum(), include_groups=False
    ).values
    state["departure_pct"] = (state["sum_actual_w"] - state["sum_normal_w"]) / state["sum_normal_w"].replace(0, np.nan) * 100
    state["rain_spatial_class"] = state["frac_rainy"].map(spatial_distribution_class)
    state["heavy_spatial_class"] = state["frac_heavy"].map(spatial_distribution_class)

    nat_g = d.groupby("date", observed=True)
    national = nat_g.apply(
        lambda x: pd.Series(
            {
                "sum_actual_w": (x[ac] * x["area_km2"]).sum(),
                "sum_normal_w": (x["daily_normal_mm"] * x["area_km2"]).sum(),
                "n_districts": len(x),
                "frac_rainy": (x[ac] >= 2.5).mean(),
                "frac_heavy": (x[ac] >= 64.5).mean(),
            }
        ),
        include_groups=False,
    ).reset_index()
    national["departure_pct"] = (national["sum_actual_w"] - national["sum_normal_w"]) / national["sum_normal_w"].replace(0, np.nan) * 100
    return state, national


def district_period_indices(df: pd.DataFrame, period: str, min_cov: float = 0.9) -> pd.DataFrame:
    """period in month, season (JJAS), year."""
    d = df.copy()
    if period == "month":
        d["period"] = d["date"].dt.to_period("M").astype(str)
        days_in = d.groupby(["district_uid", "period"], observed=True)["date"].transform("count")
        cal_days = d.groupby(["district_uid", "period"], observed=True)["date"].apply(
            lambda s: (s.max() - s.min()).days + 1
        ).reindex(d.set_index(["district_uid", "period"]).index).values
    elif period == "season":
        d["period"] = d["date"].dt.year.astype(str) + "-JJAS"
        d = d[d["date"].dt.month.isin([6, 7, 8, 9])]
        days_in = d.groupby(["district_uid", "period"], observed=True)["date"].transform("count")
        cal_days = 122  # approx JJAS
    else:
        d["period"] = d["date"].dt.year.astype(str)
        days_in = d.groupby(["district_uid", "period"], observed=True)["date"].transform("count")
        cal_days = d.groupby(["district_uid", "period"], observed=True)["date"].transform(
            lambda s: (s.max() - s.min()).days + 1
        )

    d["coverage"] = days_in / cal_days
    d["incomplete"] = d["coverage"] < min_cov

    empty = {
        "PRCPTOT": np.nan,
        "Rx1day": np.nan,
        "Rx3day": np.nan,
        "Rx5day": np.nan,
        "R2.5mm": 0,
        "R64.5mm": 0,
        "R115.6mm": 0,
        "SDII": np.nan,
        "incomplete": True,
    }

    def agg(g: pd.DataFrame) -> pd.Series:
        inc = bool(g["incomplete"].iloc[0])
        if inc:
            return pd.Series(empty)
        ac2 = _actual_col(g)
        a = g[ac2]
        return pd.Series(
            {
                "PRCPTOT": float(a.sum(skipna=True)),
                "Rx1day": float(a.max(skipna=True)),
                "Rx3day": float(a.rolling(3, min_periods=3).sum().max()),
                "Rx5day": float(a.rolling(5, min_periods=5).sum().max()),
                "R2.5mm": int((a >= 2.5).sum()),
                "R64.5mm": int((a >= 64.5).sum()),
                "R115.6mm": int((a >= 115.6).sum()),
                "SDII": float(a[a >= 2.5].mean()) if (a >= 2.5).any() else np.nan,
                "incomplete": False,
            }
        )

    out = d.groupby(["district_uid", "state_std", "district_std", "period"], observed=True).apply(agg, include_groups=False)
    if isinstance(out, pd.Series):
        out = out.unstack()
    return out.reset_index()
