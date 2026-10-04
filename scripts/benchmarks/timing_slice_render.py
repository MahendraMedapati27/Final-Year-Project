"""STEP 4 timing slice."""

from __future__ import annotations

import json

import pandas as pd

from rainfall.config import resolve_path
from rainfall.render_pool import render_dates_pool, worker_count


def main() -> None:
    d1 = pd.date_range("2025-05-25", "2025-06-23", freq="D")
    d2 = [pd.Timestamp("2021-01-31")]
    d3 = pd.date_range("2026-09-13", "2026-09-19", freq="D")
    dates = [pd.Timestamp(x) for x in d1] + d2 + [pd.Timestamp(x) for x in d3]
    root = resolve_path("outputs/maps/timing_slice")
    w = worker_count()
    print("workers", w)
    s1 = render_dates_pool(dates, root, overwrite=True, workers=w, quantize=False)
    print("first pass", s1)
    s2 = render_dates_pool(dates, root, overwrite=False, workers=w)
    print("resume pass", s2)
    n_all = pd.read_parquet(resolve_path("data/processed/rainfall_enriched.parquet"), columns=["date"])["date"].nunique()
    proj = s1["seconds_per_frame"] * n_all
    payload = {"workers": w, "slice_first": s1, "slice_resume": s2, "projected_full_seconds": proj, "projected_full_minutes": proj / 60}
    resolve_path("outputs/checkpoints/p4_timing_slice.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("projected full minutes", proj / 60)


if __name__ == "__main__":
    main()
