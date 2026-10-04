"""STEP 3a/3b only — matrix vs enriched with per-date cache."""

from __future__ import annotations

import random
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from rainfall.classes import daily_intensity_class
from rainfall.config import resolve_path
from rainfall.verify_matrix import load_matrix_meta, pg_by_shp_from_csv


def _row_from_day(day: pd.DataFrame, shp_ids: np.ndarray, pg_by_shp: dict[int, int]) -> np.ndarray:
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
        mm = row["daily_actual_mm_map"]
        if pd.isna(mm):
            continue
        _, c = daily_intensity_class(pd.Series([float(mm)]))
        out[sid_to_j[sid]] = int(c.iloc[0])
    return out


def main() -> None:
    en_path = resolve_path("data/processed/rainfall_enriched.parquet")
    npz_path = resolve_path("data/processed/render_matrix.npz")
    print("enriched_mtime_utc", datetime.fromtimestamp(en_path.stat().st_mtime, tz=timezone.utc).isoformat(), flush=True)
    print("render_matrix_mtime_utc", datetime.fromtimestamp(npz_path.stat().st_mtime, tz=timezone.utc).isoformat(), flush=True)
    print("render_matrix_newer_than_enriched", npz_path.stat().st_mtime >= en_path.stat().st_mtime, flush=True)

    npz = load_matrix_meta()
    dates_np = npz["dates"]
    shp_ids = npz["shp_ids"].astype(int)
    class_idx = npz["class_idx"]
    date_to_t = {str(np.datetime_as_string(d, unit="D")): i for i, d in enumerate(dates_np)}
    pg_by_shp = pg_by_shp_from_csv()
    cache: dict[str, np.ndarray] = {}

    def row(d: str) -> np.ndarray:
        if d not in cache:
            day = pd.read_parquet(
                en_path,
                filters=[("date", "=", pd.Timestamp(d))],
                columns=["paint_group_uid", "daily_actual_mm_map", "qc_isolated_extreme"],
            )
            cache[d] = _row_from_day(day, shp_ids, pg_by_shp)
        return cache[d]

    full_dates = ["2021-01-01", "2026-09-19", "2021-01-31", "2024-07-15", "2025-06-01"]
    full_mism = 0
    for d in full_dates:
        if d not in date_to_t:
            continue
        mism = int(np.sum(row(d) != class_idx[date_to_t[d]]))
        print(f"full_date {d} class_mismatches {mism}", flush=True)
        full_mism += mism
    print("full_date_total_mismatches", full_mism, flush=True)

    rng = random.Random(99)
    n_t, n_p = class_idx.shape
    cells = [(rng.randrange(n_t), rng.randrange(n_p)) for _ in range(5000)]
    by_t: dict[int, list[int]] = {}
    for ti, sj in cells:
        by_t.setdefault(int(ti), []).append(int(sj))
    cell_mism = 0
    for k, (ti, sjs) in enumerate(by_t.items()):
        d = str(np.datetime_as_string(dates_np[ti], unit="D"))
        exp = row(d)
        for sj in sjs:
            if exp[sj] != class_idx[ti, sj]:
                cell_mism += 1
        if (k + 1) % 200 == 0:
            print(f"random_cell_progress dates={k+1}/{len(by_t)} mism={cell_mism}", flush=True)
    print("random_5000_cell_mismatches", cell_mism, flush=True)

    excl = pd.read_parquet(
        en_path,
        filters=[("qc_isolated_extreme", "=", True)],
        columns=["date", "paint_group_uid"],
    )
    poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    pg_to_shp = poly.groupby("paint_group_uid")["shp_id"].first().to_dict()
    vals = npz["values"]
    viol = 0
    for _, er in excl.iterrows():
        sid = pg_to_shp.get(int(er["paint_group_uid"]))
        if sid is None:
            continue
        d = pd.Timestamp(er["date"]).strftime("%Y-%m-%d")
        ti = date_to_t.get(d)
        if ti is None:
            continue
        sj = int(np.where(shp_ids == sid)[0][0])
        if not np.isnan(vals[ti, sj]):
            viol += 1
    print("qc_isolated_extreme_rows", len(excl), flush=True)
    print("exclusion_matrix_nan_violations", viol, flush=True)


if __name__ == "__main__":
    main()
