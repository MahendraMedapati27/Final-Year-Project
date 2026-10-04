"""STEP 5 full render (background entrypoint)."""

from __future__ import annotations

import argparse
import json

import pandas as pd

from rainfall.config import resolve_path
from rainfall.render_pool import render_dates_pool, worker_count


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-render all dates even if PNG exists (default: skip existing).",
    )
    args = ap.parse_args()
    en = pd.read_parquet(resolve_path("data/processed/rainfall_enriched.parquet"), columns=["date"])
    en["date"] = pd.to_datetime(en["date"])
    dates = sorted(en["date"].unique())
    cal = pd.date_range(dates[0], dates[-1], freq="D")
    missing = [d for d in cal if d not in set(dates)]
    pd.DataFrame({"missing_date": missing}).to_csv(resolve_path("outputs/maps/missing_dates.csv"), index=False)
    root = resolve_path("outputs/maps/daily_actual")
    w = worker_count()
    print("workers", w, "n_dates", len(dates), flush=True)
    summary = render_dates_pool(
        [pd.Timestamp(d) for d in dates],
        root,
        overwrite=args.overwrite,
        workers=w,
    )
    resolve_path("outputs/checkpoints/p5_full_render.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(summary, flush=True)


if __name__ == "__main__":
    main()
