"""P3 resumable batch map rendering."""



from __future__ import annotations



import csv

import json

import logging

import multiprocessing as mp

import os

import sys

import time

from pathlib import Path



import pandas as pd



from rainfall.config import load_config, resolve_path

from rainfall.render import build_render_matrix

from rainfall.render_daily import DailyMapRenderer



logger = logging.getLogger(__name__)



_worker_renderer: DailyMapRenderer | None = None

_worker_cfg: dict | None = None





def _worker_init() -> None:

    global _worker_renderer, _worker_cfg

    for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):

        os.environ.setdefault(_var, "2")

    _worker_cfg = load_config()

    _worker_renderer = DailyMapRenderer(cfg=_worker_cfg)





def _render_one(args: tuple[str, str, bool]) -> dict:

    date_s, out_s, overwrite = args

    out = Path(out_s)

    if out.exists() and not overwrite:

        return {"date": date_s, "skipped": True, "path": str(out)}

    r = _worker_renderer

    assert r is not None

    d = pd.Timestamp(date_s)

    cols = ["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std", "qc_isolated_extreme"]

    day = pd.read_parquet(resolve_path(_worker_cfg["paths"]["processed_enriched"]), filters=[("date", "=", d)], columns=cols)

    dp = r.draw_date(d, day)

    meta = r.save(out)

    meta.update(

        {

            "date": date_s,

            "path": str(out),

            "skipped": False,

            "n_districts_with_data": len(dp.shp_mm),

            "n_no_data": sum(1 for v in dp.shp_class.values() if v < 0),

            "n_heavy": int(sum(1 for v in dp.shp_mm.values() if v >= 64.5)),

            "n_parent": dp.n_parent,

            "n_excluded_suspect": dp.n_excluded_suspect,

        }

    )

    if dp.shp_mm:

        import numpy as np



        areas = {sid: r.geom.area_by_shp.get(sid, 0) for sid in dp.shp_mm}

        vals = pd.Series(dp.shp_mm)

        w = pd.Series(areas).reindex(vals.index).fillna(0)

        meta["area_weighted_mean_mm"] = float(np.average(vals, weights=w))

        meta["min_mm"] = float(vals.min())

        meta["max_mm"] = float(vals.max())

    return meta





def output_path(maps_root: Path, date: pd.Timestamp) -> Path:

    return maps_root / f"{date.year:04d}" / f"{date.month:02d}" / f"rainfall_actual_{date.date()}.png"





def render_dates(

    dates: list[pd.Timestamp],

    workers: int | None = None,

    overwrite: bool = False,

    rebuild_matrix: bool = True,

) -> dict:

    cfg = load_config()

    maps_root = resolve_path(cfg["outputs"]["maps_daily_actual"])

    err_log = resolve_path("logs/render_errors.csv")

    manifest_path = maps_root / "manifest.csv"



    if rebuild_matrix:

        en = pd.read_parquet(resolve_path(cfg["paths"]["processed_enriched"]), columns=["date", "paint_group_uid", "daily_actual_mm_map"])

        poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))

        build_render_matrix(en, poly)



    if workers is None:
        # Each process loads GPKG + figure; multi-process OOM on Windows.
        n_workers = 1 if sys.platform == "win32" else max(1, (os.cpu_count() or 4) - 1)
    else:
        n_workers = workers

    tasks = [(str(d.date()), str(output_path(maps_root, d)), overwrite) for d in dates]



    t0 = time.perf_counter()

    if n_workers <= 1:

        _worker_init()

        results = [_render_one(t) for t in tasks]

    else:

        with mp.Pool(n_workers, initializer=_worker_init) as pool:

            results = pool.map(_render_one, tasks, chunksize=4)

    elapsed = time.perf_counter() - t0

    rendered = [r for r in results if not r.get("skipped")]

    skipped = [r for r in results if r.get("skipped")]



    rows = []

    if manifest_path.exists():

        rows = pd.read_csv(manifest_path).to_dict("records")

    by_date = {r["date"]: r for r in rows}

    for r in results:

        if r.get("skipped"):

            continue

        by_date[r["date"]] = {k: r.get(k) for k in r if k not in ("skipped",)}

    pd.DataFrame(by_date.values()).sort_values("date").to_csv(manifest_path, index=False)



    failures = [r for r in results if r.get("error")]

    if failures:

        with err_log.open("a", newline="", encoding="utf-8") as f:

            w = csv.DictWriter(f, fieldnames=["date", "error"])

            if err_log.stat().st_size == 0:

                w.writeheader()

            w.writerows(failures)



    summary = {

        "n_dates": len(dates),

        "n_rendered": len(rendered),

        "n_skipped": len(skipped),

        "seconds_total": elapsed,

        "seconds_per_frame_rendered": elapsed / max(len(rendered), 1),
        "seconds_per_frame_wall": elapsed / max(len(dates), 1),

        "workers": n_workers,

    }

    resolve_path("outputs/checkpoints/p3_slice.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary

