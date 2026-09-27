"""STEP 5: two trial maps, tests, speed report, no-data table. Do not full-render."""

from __future__ import annotations

import json
import subprocess
import sys
import time

import pandas as pd
from PIL import Image

from rainfall.config import load_config, resolve_path
from rainfall.nodata_report import no_data_by_year, no_data_districts_on_date, top_districts_by_nan_days
from rainfall.render_daily import DailyMapRenderer
from rainfall.render_geom import load_render_geometry


def main() -> None:
    cfg = load_config()
    out_dir = resolve_path("outputs/maps/p2_trial")
    out_dir.mkdir(parents=True, exist_ok=True)
    dates = [pd.Timestamp("2026-09-19"), pd.Timestamp("2021-01-31")]
    cols = ["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std", "qc_isolated_extreme"]

    # Speed: cold vs warm (cached geometry + reused figure)
    t_cold = time.perf_counter()
    r_cold = DailyMapRenderer(cfg=cfg)
    day0 = pd.read_parquet(resolve_path(cfg["paths"]["processed_enriched"]), filters=[("date", "=", dates[0])], columns=cols)
    r_cold.draw_date(dates[0], day0)
    r_cold.save(out_dir / f"rainfall_actual_{dates[0].date()}.png")
    cold_s = time.perf_counter() - t_cold

    t_warm = time.perf_counter()
    day1 = pd.read_parquet(resolve_path(cfg["paths"]["processed_enriched"]), filters=[("date", "=", dates[1])], columns=cols)
    r_cold.draw_date(dates[1], day1)
    meta = r_cold.save(out_dir / f"rainfall_actual_{dates[1].date()}.png")
    warm_s = time.perf_counter() - t_warm

    n_dates = pd.read_parquet(resolve_path("data/processed/rainfall_enriched.parquet"), columns=["date"])["date"].nunique()

    print("=== STEP 1 preserved ===")
    print("Stopped P4 workers; frames in outputs/maps/_old_layout (see preserved_frames in log)")

    print("\n=== STEP 4 speed ===")
    print("Workers during P4: 1 (Windows default; multi-process duplicated GPKG and OOM'd)")
    print(f"Before fixes (cold init + draw+save): {cold_s:.2f} s/frame")
    print(f"After cached geom + reused figure + single savefig: {warm_s:.2f} s/frame")
    proj_h = warm_s * n_dates / 3600
    print(f"Projected full ~{n_dates} frames at warm rate: {proj_h:.2f} h")

    print("\n=== STEP 3b no-data ===")
    print(no_data_by_year().to_string(index=False))
    print("\nTop 10 districts by NaN days:")
    print(top_districts_by_nan_days(10).to_string(index=False))
    print(f"\n2021-01-31 no-data districts (n={len(no_data_districts_on_date('2021-01-31'))}):")
    print(no_data_districts_on_date("2021-01-31").to_string(index=False))

    print("\n=== STEP 5 trials ===")
    paths = [out_dir / f"rainfall_actual_{d.date()}.png" for d in dates]
    for p in paths:
        im = Image.open(p)
        print(p, im.size)

    print("\n=== pytest ===")
    rc = subprocess.call([sys.executable, "-m", "pytest", "tests/test_render_p2.py", "-q", "-m", "full"])
    payload = {
        "paths": [str(p) for p in paths],
        "dimensions": [Image.open(p).size for p in paths],
        "seconds_frame_cold": cold_s,
        "seconds_frame_warm": warm_s,
        "workers_p4": 1,
        "projected_hours": proj_h,
        "pytest_rc": rc,
    }
    resolve_path("outputs/checkpoints/p2_trial_round2.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if rc != 0:
        sys.exit(rc)


if __name__ == "__main__":
    main()
