"""Rebuild expected class matrix from enriched parquet (independent of render_matrix.npz)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from rainfall.classes import daily_intensity_class
from rainfall.config import resolve_path


def rebuild_classes_for_date(
    date: pd.Timestamp,
    *,
    shp_ids: np.ndarray,
    pg_by_shp: dict[int, int],
    enriched_path=None,
    ac: str = "daily_actual_mm_map",
) -> np.ndarray:
    """One row of class_idx aligned with shp_ids."""
    enriched_path = enriched_path or resolve_path("data/processed/rainfall_enriched.parquet")
    day = pd.read_parquet(
        enriched_path,
        filters=[("date", "=", pd.Timestamp(date))],
        columns=["paint_group_uid", ac, "qc_isolated_extreme"],
    )
    by_pg = day.set_index("paint_group_uid")
    out = np.full(len(shp_ids), -1, dtype=np.int8)
    sid_to_j = {int(s): j for j, s in enumerate(shp_ids)}
    for sid in shp_ids:
        sid = int(sid)
        pg = pg_by_shp.get(sid, -1)
        if pg not in by_pg.index:
            continue
        row = by_pg.loc[pg]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        if "qc_isolated_extreme" in by_pg.columns and bool(row.get("qc_isolated_extreme", False)):
            continue
        mm = row[ac]
        if pd.isna(mm):
            continue
        _, c = daily_intensity_class(pd.Series([float(mm)]))
        out[sid_to_j[sid]] = int(c.iloc[0])
    return out


def load_matrix_meta():
    npz = np.load(resolve_path("data/processed/render_matrix.npz"), allow_pickle=False)
    return npz


def pg_by_shp_from_csv() -> dict[int, int]:
    poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    return poly.set_index("shp_id")["paint_group_uid"].astype(int).to_dict()
