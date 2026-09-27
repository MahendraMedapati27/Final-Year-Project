"""Extreme rainfall review and daily_actual_mm_map (P1b.3)."""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from libpysal.weights import Queen

from rainfall.config import load_config, resolve_path
from rainfall.dedupe import _prepare_districts_for_weights


def _queen_by_shp() -> dict[int, list[int]]:
    cfg = load_config()
    gdf = _prepare_districts_for_weights(gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="districts"))
    w = Queen.from_dataframe(gdf, use_index=False, ids=gdf["shp_id"].astype(int).tolist())
    return {int(k): [int(n) for n in v] for k, v in w.neighbors.items()}


def build_extreme_review(enriched: pd.DataFrame | None = None) -> pd.DataFrame:
    cfg = load_config()
    if enriched is None:
        enriched = pd.read_parquet(resolve_path(cfg["paths"]["processed_enriched"]))
    sub = enriched[enriched["daily_actual_mm"] > 500].copy()
    neigh = _queen_by_shp()
    shp_dist = enriched.drop_duplicates(["state", "district"]).set_index("shp_id")
    day_lookup = enriched.set_index(["shp_id", "date"])["daily_actual_mm"]

    rows = []
    for _, r in sub.iterrows():
        sid = int(r["shp_id"]) if pd.notna(r.get("shp_id")) else -1
        dt = pd.Timestamp(r["date"])
        n_vals = []
        for ns in neigh.get(sid, []):
            try:
                v = day_lookup.loc[(ns, dt)]
                if isinstance(v, pd.Series):
                    v = v.dropna()
                    if len(v) == 0:
                        continue
                    v = v.iloc[0]
                if pd.notna(v):
                    n_vals.append(float(v))
            except KeyError:
                pass
        n_med = float(np.median(n_vals)) if n_vals else np.nan
        n_max = float(np.max(n_vals)) if n_vals else np.nan
        prev = next_ = np.nan
        if sid > 0:
            def _one(key):
                try:
                    v = day_lookup.loc[key]
                    if isinstance(v, pd.Series):
                        v = v.dropna()
                        return float(v.iloc[0]) if len(v) else np.nan
                    return float(v)
                except KeyError:
                    return np.nan

            prev = _one((sid, dt - pd.Timedelta(days=1)))
            next_ = _one((sid, dt + pd.Timedelta(days=1)))
        val = float(r["daily_actual_mm"])
        plausible = (n_med > 100) or (prev > 200 or next_ > 200) or (n_med >= 50 and val < 2 * n_med)
        isolated = (n_med < 50 if pd.notna(n_med) else True) and not (prev > 200 or next_ > 200)
        if pd.isna(n_med) and n_vals == []:
            isolated = True
        klass = "plausible" if plausible and not isolated else ("isolated_suspect" if isolated else "plausible")
        rows.append(
            {
                "state": r["state"],
                "district": r["district"],
                "date": dt.date().isoformat(),
                "daily_actual_mm": val,
                "daily_normal_mm": r.get("daily_normal_mm"),
                "neighbour_median_mm": n_med,
                "neighbour_max_mm": n_max,
                "prev_day_mm": prev,
                "next_day_mm": next_,
                "classification": klass,
            }
        )
    rep = pd.DataFrame(rows)
    rep.to_csv(resolve_path("outputs/tables/extreme_values_review.csv"), index=False)
    return rep


def apply_map_column(df: pd.DataFrame, review: pd.DataFrame | None = None) -> pd.DataFrame:
    if review is None:
        review = pd.read_csv(resolve_path("outputs/tables/extreme_values_review.csv"))
    df = df.copy()
    df["daily_actual_mm_map"] = df["daily_actual_mm"]
    df["qc_isolated_extreme"] = False
    suspects = review[review["classification"] == "isolated_suspect"]
    if len(suspects):
        keys = set(zip(suspects["state"], suspects["district"], pd.to_datetime(suspects["date"])))
        mask = df.apply(lambda r: (r["state"], r["district"], pd.Timestamp(r["date"])) in keys, axis=1)
        df.loc[mask, "qc_isolated_extreme"] = True
        df.loc[mask, "daily_actual_mm_map"] = np.nan
    meta = {
        "n_extreme_over_500": int((df["daily_actual_mm"] > 500).sum()),
        "n_excluded_map": int(df["qc_isolated_extreme"].sum()),
    }
    resolve_path("outputs/checkpoints/p1b_extremes.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return df
