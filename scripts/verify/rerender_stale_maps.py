"""Re-render PNGs older than design cutoff (overwrite) + manifest merge."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from rainfall.config import resolve_path
from rainfall.render_pool import render_dates_pool, worker_count


def design_cutoff() -> float:
    paths = [
        resolve_path("data/processed/render_matrix.npz"),
        resolve_path("src/rainfall/render_daily.py"),
        resolve_path("src/rainfall/render_engine.py"),
        resolve_path("config/config.yaml"),
        resolve_path("src/rainfall/palette_lab.py"),
    ]
    for p in resolve_path("outputs/render_cache").rglob("geometry.pkl"):
        paths.append(p)
    return max(p.stat().st_mtime for p in paths if p.exists())


def main() -> None:
    cutoff = design_cutoff()
    print("design_cutoff_utc", datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat(), flush=True)
    root = resolve_path("outputs/maps/daily_actual")
    stale: list[pd.Timestamp] = []
    for p in root.rglob("rainfall_actual_*.png"):
        if p.stat().st_mtime < cutoff:
            d = p.stem.replace("rainfall_actual_", "")
            stale.append(pd.Timestamp(d))
    stale = sorted(set(stale))
    print("stale_count", len(stale), flush=True)
    if not stale:
        print("nothing to re-render")
        return
    w = worker_count()
    summary = render_dates_pool(stale, root, overwrite=True, workers=w)
    print(summary, flush=True)
    resolve_path("outputs/checkpoints/verify_rerender_stale.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
