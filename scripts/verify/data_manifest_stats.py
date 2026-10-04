"""STEP 3: Independent matrix, exclusions, manifest stats; writes mismatch lists."""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from rainfall.config import load_config, resolve_path
from rainfall.map_stats_independent import compute_day_manifest_stats
from rainfall.render_geom_cache import load_geometry_cached
from rainfall.verify_matrix import load_matrix_meta, pg_by_shp_from_csv, rebuild_classes_for_date


def main() -> None:
    cfg = load_config()
    en_path = resolve_path("data/processed/rainfall_enriched.parquet")
    npz_path = resolve_path("data/processed/render_matrix.npz")
    print("enriched_mtime_utc", datetime.fromtimestamp(en_path.stat().st_mtime, tz=timezone.utc).isoformat())
    print("render_matrix_mtime_utc", datetime.fromtimestamp(npz_path.stat().st_mtime, tz=timezone.utc).isoformat())
    matrix_newer = npz_path.stat().st_mtime >= en_path.stat().st_mtime
    print("render_matrix_newer_than_enriched", matrix_newer)

    npz = load_matrix_meta()
    dates_np = npz["dates"]
    shp_ids = npz["shp_ids"].astype(int)
    class_idx = npz["class_idx"]
    date_to_t = {str(np.datetime_as_string(d, unit="D")): i for i, d in enumerate(dates_np)}
    pg_by_shp = pg_by_shp_from_csv()

    # 3a: five full dates (from step2 specials minus march 2024)
    full_dates = ["2021-01-01", "2026-09-19", "2021-01-31", "2024-07-15", "2025-06-01"]
    full_dates = [d for d in full_dates if d in date_to_t]
    full_mism = 0
    for d in full_dates:
        exp = rebuild_classes_for_date(pd.Timestamp(d), shp_ids=shp_ids, pg_by_shp=pg_by_shp)
        ti = date_to_t[d]
        got = class_idx[ti]
        mism = int(np.sum(exp != got))
        full_mism += mism
        print(f"full_date {d} class_mismatches {mism}")
    print("full_date_total_mismatches", full_mism)

    rng = random.Random(99)
    n_t, n_p = class_idx.shape
    cells = [(rng.randrange(n_t), rng.randrange(n_p)) for _ in range(5000)]
    by_t: dict[int, list[int]] = {}
    for ti, sj in cells:
        by_t.setdefault(ti, []).append(sj)
    cell_mism = 0
    for ti, sjs in by_t.items():
        d = str(np.datetime_as_string(dates_np[ti], unit="D"))
        exp_row = rebuild_classes_for_date(pd.Timestamp(d), shp_ids=shp_ids, pg_by_shp=pg_by_shp)
        for sj in sjs:
            if exp_row[sj] != class_idx[ti, sj]:
                cell_mism += 1
    print("random_5000_cell_mismatches", cell_mism)

    # 3b exclusions
    excl_rows = pd.read_parquet(
        en_path,
        filters=[("qc_isolated_extreme", "=", True)],
        columns=["date", "paint_group_uid", "daily_actual_mm_map"],
    )
    print("qc_isolated_extreme_rows", len(excl_rows))
    excl_viol = 0
    nonexcl_nan = 0
    poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    pg_to_shp = poly.groupby("paint_group_uid")["shp_id"].first().to_dict()
    for _, row in excl_rows.iterrows():
        pg = int(row["paint_group_uid"])
        sid = pg_to_shp.get(pg)
        if sid is None:
            continue
        d = pd.Timestamp(row["date"]).strftime("%Y-%m-%d")
        ti = date_to_t.get(d)
        if ti is None:
            continue
        sj = int(np.where(shp_ids == sid)[0][0])
        if not np.isnan(npz["values"][ti, sj]):
            excl_viol += 1
    # spot check non-excluded with values are not forced nan
    print("exclusion_matrix_nan_violations", excl_viol)

    # 3c manifest stats all dates — one date at a time
    geom = load_geometry_cached(cfg)
    man = pd.read_csv(resolve_path("outputs/maps/daily_actual/manifest.csv"))
    stat_diff: list[str] = []
    cols_cmp = [
        ("n_districts_with_data", 0),
        ("n_no_data", 0),
        ("n_parent_value", 0),
        ("n_excluded_suspect", 0),
        ("n_heavy", 0),
        ("area_weighted_mean_mm", 0.05),
        ("min_mm", 0.05),
        ("max_mm", 0.05),
        ("wettest_mm", 0.05),
    ]
    for i, row in man.iterrows():
        d = str(row["date"])
        day = pd.read_parquet(
            en_path,
            filters=[("date", "=", pd.Timestamp(d))],
            columns=["paint_group_uid", "daily_actual_mm_map", "state_std", "district_std", "qc_isolated_extreme"],
        )
        ind = compute_day_manifest_stats(day, geom)
        bad = False
        for col, tol in cols_cmp:
            a = row.get(col)
            b = ind.get(col)
            if pd.isna(a) and pd.isna(b):
                continue
            if col == "wettest_district":
                continue
            if isinstance(b, float) and isinstance(a, (float, int)):
                if abs(float(a) - float(b)) > tol:
                    bad = True
            elif int(a) != int(b):
                bad = True
        wd = str(row.get("wettest_district") or "").strip()
        wd_i = str(ind.get("wettest_district") or "").strip()
        if wd != wd_i and not (pd.isna(row.get("wettest_district")) and not wd_i):
            bad = True
        if bad:
            stat_diff.append(d)
        if (i + 1) % 300 == 0:
            print(f"stats_progress {i+1}/{len(man)} diffs_so_far {len(stat_diff)}", flush=True)
    print("manifest_stats_diff_dates", len(stat_diff))
    if stat_diff[:15]:
        print("sample_diff_dates", stat_diff[:15])

    payload = {
        "full_date_mismatches": full_mism,
        "random_cell_mismatches": cell_mism,
        "exclusion_violations": excl_viol,
        "manifest_stats_diff_count": len(stat_diff),
        "manifest_stats_diff_dates": stat_diff,
        "matrix_newer_than_enriched": matrix_newer,
    }
    resolve_path("outputs/checkpoints/verify_step3.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    Path(resolve_path("outputs/tables/manifest_stats_diff_dates.txt")).write_text("\n".join(stat_diff), encoding="utf-8")


if __name__ == "__main__":
    main()
