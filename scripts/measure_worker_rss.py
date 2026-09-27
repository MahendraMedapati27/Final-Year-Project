"""Measure worker RSS after 3 legacy frames."""

from __future__ import annotations

import os
import time

import psutil

from rainfall.config import resolve_path
from rainfall.render_engine import FrozenRenderer


def main() -> None:
    proc = psutil.Process(os.getpid())
    rss0 = proc.memory_info().rss / 1e6
    print(f"RSS before init MB: {rss0:.0f}")
    r = FrozenRenderer()
    rss1 = proc.memory_info().rss / 1e6
    print(f"RSS after init MB: {rss1:.0f}")
    dates = ["2026-09-19", "2021-01-31", "2025-05-31"]
    out = resolve_path("outputs/maps/rss_probe")
    out.mkdir(parents=True, exist_ok=True)
    for d in dates:
        r.render_date(__import__("pandas").Timestamp(d), out / f"{d}.png")
    rss2 = proc.memory_info().rss / 1e6
    print(f"RSS after 3 frames MB: {rss2:.0f}")
    print(f"delta_init_MB: {rss1-rss0:.0f}")
    print(f"rss_per_worker_GB: {rss2/1024:.2f}")


if __name__ == "__main__":
    main()
