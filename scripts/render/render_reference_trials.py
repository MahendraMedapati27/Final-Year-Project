"""Render exactly two P2 trial maps (professor dates)."""

from __future__ import annotations

from pathlib import Path

import rainfall.render_geom as rg

rg._CACHED_GEOM = None

import pandas as pd

from rainfall.config import load_config, resolve_path
from rainfall.render_daily import DailyMapRenderer

DATES = [pd.Timestamp("2026-09-19"), pd.Timestamp("2021-01-31")]
COLS = ["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std", "qc_isolated_extreme"]


def main() -> None:
    cfg = load_config()
    out = resolve_path("outputs/maps/p2_trial")
    out.mkdir(parents=True, exist_ok=True)
    r = DailyMapRenderer(cfg=cfg)
    en = resolve_path(cfg["paths"]["processed_enriched"])
    for d in DATES:
        day = pd.read_parquet(en, filters=[("date", "=", d)], columns=COLS)
        r.draw_date(d, day)
        p = out / f"rainfall_actual_{d.date()}.png"
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp()) / p.name
        meta = r.save(tmp)
        shutil.copy2(tmp, p)
        print(p, meta["size"], f"{meta['seconds_total']:.1f}s")


if __name__ == "__main__":
    main()
