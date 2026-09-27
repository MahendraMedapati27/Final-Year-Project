"""Multiprocess frozen render pool (spawn, no GPKG in workers)."""

from __future__ import annotations

import csv
import logging
import os
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd
import psutil

from rainfall.config import load_config, resolve_path
from rainfall.render_engine import FrozenRenderer
from rainfall.render_geom_cache import ensure_geometry_cache

logger = logging.getLogger(__name__)

_worker: FrozenRenderer | None = None


def _worker_init() -> None:
    global _worker
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[v] = "1"
    cfg = load_config()
    ensure_geometry_cache(cfg)
    _worker = FrozenRenderer(cfg=cfg)


def _render_task(args: tuple[str, str, bool, bool]) -> dict:
    date_s, out_s, overwrite, quantize = args
    out = Path(out_s)
    if out.exists() and not overwrite:
        return {"date": date_s, "skipped": True}
    assert _worker is not None
    try:
        meta = _worker.render_date(pd.Timestamp(date_s), out, quantize=quantize)
    except MemoryError as e:
        return {"date": date_s, "error": f"MemoryError: {e}", "skipped": False}
    except Exception as e:
        return {"date": date_s, "error": str(e), "skipped": False}
    meta["skipped"] = False
    meta["path"] = str(out)
    return meta


def _manifest_row(meta: dict) -> dict:
    """Normalize render metadata to manifest.csv columns."""
    return {
        "date": meta.get("date"),
        "path": meta.get("path"),
        "n_districts_with_data": meta.get("n_districts_with_data"),
        "n_no_data": meta.get("n_no_data"),
        "n_parent_value": meta.get("n_parent_value", meta.get("n_parent")),
        "n_excluded_suspect": meta.get("n_excluded_suspect"),
        "min_mm": meta.get("min_mm"),
        "max_mm": meta.get("max_mm"),
        "area_weighted_mean_mm": meta.get("area_weighted_mean_mm"),
        "n_heavy": meta.get("n_heavy"),
        "wettest_district": meta.get("wettest_district"),
        "wettest_mm": meta.get("wettest_mm"),
    }


def worker_count(rss_per_worker_gb: float | None = None) -> int:
    """RAM budget: leave 1 GB headroom; default ~0.59 GB/worker from legacy pickle path."""
    avail_gb = psutil.virtual_memory().available / (1024**3)
    cpu = max(1, (os.cpu_count() or 4) - 1)
    rss = rss_per_worker_gb if rss_per_worker_gb is not None else 0.59
    by_ram = int((avail_gb - 1.0) // rss) if rss > 0 else 1
    return max(1, min(cpu, by_ram))


def _log_memory_watchdog(prog_log: Path, n_workers: int) -> None:
    vm = psutil.virtual_memory()
    line = (
        f"watchdog avail_GB={vm.available / (1024**3):.2f} "
        f"rss_main_MB={psutil.Process(os.getpid()).memory_info().rss / 1e6:.0f} workers={n_workers}\n"
    )
    prog_log.parent.mkdir(parents=True, exist_ok=True)
    with prog_log.open("a", encoding="utf-8") as f:
        f.write(line)


def render_dates_pool(
    dates: list[pd.Timestamp],
    maps_root: Path,
    *,
    overwrite: bool = False,
    quantize: bool = False,
    workers: int | None = None,
    chunk_log_every: int = 50,
) -> dict:
    cfg = load_config()
    ensure_geometry_cache(cfg)
    n_workers = workers if workers is not None else worker_count()
    err_log = resolve_path("logs/render_errors.csv")
    prog_log = resolve_path("logs/render_progress.log")
    manifest_path = maps_root / "manifest.csv"

    def out_path(d: pd.Timestamp) -> Path:
        return maps_root / f"{d.year:04d}" / f"{d.month:02d}" / f"rainfall_actual_{d.date()}.png"

    pending = [(str(d.date()), str(out_path(d)), overwrite, quantize) for d in dates]
    t0 = time.perf_counter()
    results: list[dict] = []
    import multiprocessing as mp

    def _watchdog_stop() -> None:
        return False

    stop_flag = {"stop": False}

    def _watchdog_loop() -> None:
        while not stop_flag["stop"]:
            _log_memory_watchdog(prog_log, n_workers)
            for _ in range(60):
                if stop_flag["stop"]:
                    break
                time.sleep(1)

    wd = threading.Thread(target=_watchdog_loop, daemon=True)
    wd.start()

    while pending and n_workers >= 1:
        batch = pending
        pending = []
        mem_errors: list[tuple] = []
        try:
            with ProcessPoolExecutor(
                max_workers=n_workers,
                mp_context=mp.get_context("spawn"),
                initializer=_worker_init,
            ) as ex:
                for i, meta in enumerate(ex.map(_render_task, batch, chunksize=25), start=1):
                    if meta.get("error"):
                        with err_log.open("a", newline="", encoding="utf-8") as f:
                            w = csv.DictWriter(f, fieldnames=["date", "error"])
                            if err_log.stat().st_size == 0:
                                w.writeheader()
                            w.writerow({"date": meta.get("date", "?"), "error": meta["error"]})
                        if "MemoryError" in str(meta.get("error", "")):
                            ds = meta.get("date")
                            mem_errors.extend(t for t in batch if t[0] == ds)
                            continue
                    results.append(meta)
                    if len(results) % chunk_log_every == 0:
                        elapsed = time.perf_counter() - t0
                        rate = len(results) / elapsed * 60 if elapsed else 0
                        eta_min = (len(dates) - len(results)) / (len(results) / elapsed) / 60 if results else 0
                        with prog_log.open("a", encoding="utf-8") as f:
                            f.write(
                                f"{len(results)}/{len(dates)} frames  {rate:.1f} frames/min  "
                                f"ETA {eta_min:.1f} min  workers={n_workers}\n"
                            )
        except MemoryError:
            n_workers = max(1, n_workers - 1)
            pending = batch
            continue
        if mem_errors and n_workers > 1:
            n_workers -= 1
            pending = mem_errors
        else:
            pending = []

    stop_flag["stop"] = True
    wd.join(timeout=2)

    elapsed = time.perf_counter() - t0
    rendered = [r for r in results if not r.get("skipped") and not r.get("error")]
    skipped = [r for r in results if r.get("skipped")]
    spf = elapsed / max(len(rendered), 1)
    summary = {
        "n_dates": len(dates),
        "n_rendered": len(rendered),
        "n_skipped": len(skipped),
        "seconds_total": elapsed,
        "seconds_per_frame": spf,
        "frames_per_min": len(rendered) / elapsed * 60 if elapsed else 0,
        "workers": n_workers,
        "engine": "legacy_frozen_pillow",
    }
    rows = {}
    if manifest_path.exists():
        for r in pd.read_csv(manifest_path).to_dict(orient="records"):
            rows[r["date"]] = r
    for r in results:
        if r.get("skipped") or r.get("error"):
            continue
        rows[r["date"]] = _manifest_row(r)
    cols = [
        "date",
        "path",
        "n_districts_with_data",
        "n_no_data",
        "n_parent_value",
        "n_excluded_suspect",
        "min_mm",
        "max_mm",
        "area_weighted_mean_mm",
        "n_heavy",
        "wettest_district",
        "wettest_mm",
    ]
    df = pd.DataFrame(rows.values())
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df.sort_values("date")[cols].to_csv(manifest_path, index=False)
    return summary
