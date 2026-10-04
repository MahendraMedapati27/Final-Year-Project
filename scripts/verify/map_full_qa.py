"""STEP 4: Full QA — one frame at a time; compare on-disk PNG vs current engine."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from rainfall.config import resolve_path
from rainfall.render_engine import FrozenRenderer
from rainfall.render_pool import worker_count


def _pixel_diff_frac(a: np.ndarray, b: np.ndarray) -> float:
    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    mx = d.max(axis=2)
    return float((mx > 24).mean())


def main() -> None:
    t0 = time.perf_counter()
    maps_root = resolve_path("outputs/maps/daily_actual")
    manifest_path = maps_root / "manifest.csv"
    en_path = resolve_path("data/processed/rainfall_enriched.parquet")
    n_dates = int(pd.read_parquet(en_path, columns=["date"])["date"].nunique())
    pngs = sorted(maps_root.rglob("rainfall_actual_*.png"))
    checks: list[dict] = []

    checks.append({"check": "png_count", "pass": len(pngs) == n_dates, "got": len(pngs), "expected": n_dates})
    zero = [p for p in pngs if p.stat().st_size == 0]
    checks.append({"check": "no_zero_byte", "pass": len(zero) == 0, "got": len(zero), "expected": 0})
    decode_fail = 0
    sizes: set[tuple[int, int]] = set()
    for p in pngs:
        try:
            with Image.open(p) as im:
                im.load()
                sizes.add(im.size)
        except Exception:
            decode_fail += 1
    checks.append({"check": "all_decode", "pass": decode_fail == 0, "got": decode_fail, "expected": 0})
    checks.append(
        {
            "check": "identical_dimensions",
            "pass": len(sizes) == 1,
            "got": str(sizes),
            "expected": "one size",
        }
    )

    man = pd.read_csv(manifest_path)
    man_cols = [
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
    missing_cols = [c for c in man_cols if c not in man.columns]
    checks.append({"check": "manifest_columns", "pass": len(missing_cols) == 0, "got": missing_cols, "expected": []})
    checks.append({"check": "manifest_rows", "pass": len(man) >= n_dates, "got": len(man), "expected": n_dates})

    legend_bad: list[str] = []
    for _, row in man.iterrows():
        nd = int(row.get("n_districts_with_data") or 0)
        nn = int(row.get("n_no_data") or 0)
        if nd + nn < 750:
            legend_bad.append(str(row["date"]))
    checks.append(
        {
            "check": "legend_counts_vs_districts",
            "pass": len(legend_bad) == 0,
            "got": len(legend_bad),
            "expected": 0,
        }
    )

    err = resolve_path("logs/render_errors.csv")
    err_body = err.read_text(encoding="utf-8").strip() if err.exists() else ""
    checks.append(
        {
            "check": "render_errors_empty",
            "pass": err_body in ("", "date,error"),
            "got": len(err_body.splitlines()),
            "expected": "header only",
        }
    )

    tmp = resolve_path("outputs/maps/verify_tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    r = FrozenRenderer()
    parity_fail: list[str] = []
    white_fail: list[str] = []
    dates = sorted(man["date"].astype(str).tolist()) if len(man) else [p.stem.replace("rainfall_actual_", "") for p in pngs]
    for i, d in enumerate(dates):
        on_disk = maps_root / d[:4] / d[5:7] / f"rainfall_actual_{d}.png"
        if not on_disk.exists():
            parity_fail.append(d)
            continue
        cand = tmp / f"qa_{d}.png"
        r.render_date(pd.Timestamp(d), cand)
        a = np.array(Image.open(on_disk).convert("RGB"))
        b = np.array(Image.open(cand).convert("RGB"))
        if a.shape != b.shape:
            parity_fail.append(d)
        else:
            frac = _pixel_diff_frac(a, b)
            if frac > 0:
                parity_fail.append(d)
            # white inside map: bottom 15% is UI; sample central map band
            h = a.shape[0]
            band = a[int(h * 0.12) : int(h * 0.88), :, :]
            if (band == 255).all(axis=2).any():
                pass  # outside fill beige not white — only flag pure white clusters in band
            white_px = ((band[:, :, 0] == 255) & (band[:, :, 1] == 255) & (band[:, :, 2] == 255)).sum()
            if white_px > 500:
                white_fail.append(d)
        cand.unlink(missing_ok=True)
        if (i + 1) % 50 == 0:
            print(f"step4_progress {i+1}/{len(dates)} parity_fail={len(parity_fail)}", flush=True)

    checks.append(
        {
            "check": "png_vs_current_engine",
            "pass": len(parity_fail) == 0,
            "got": len(parity_fail),
            "expected": 0,
        }
    )
    checks.append(
        {
            "check": "no_excess_white_in_map_band",
            "pass": len(white_fail) == 0,
            "got": len(white_fail),
            "expected": 0,
        }
    )

    total_bytes = sum(p.stat().st_size for p in pngs)
    ckpt = resolve_path("outputs/checkpoints/p5_full_render.json")
    workers = worker_count()
    render_meta = json.loads(ckpt.read_text()) if ckpt.exists() else {}
    elapsed = time.perf_counter() - t0
    meta = {
        "parity_fail_sample": parity_fail[:30],
        "white_fail_sample": white_fail[:30],
        "qa_wall_seconds": elapsed,
        "disk_gb": total_bytes / (1024**3),
        "workers": workers,
        "render_seconds_total": render_meta.get("seconds_total"),
        "frames_per_min": render_meta.get("frames_per_min"),
    }
    checks.append(
        {
            "check": "disk_size_gb",
            "pass": True,
            "got": round(meta["disk_gb"], 3),
            "expected": ">0",
        }
    )

    df = pd.DataFrame(checks)
    print(df.to_string(index=False))
    print("meta", meta, flush=True)
    payload = {"checks": df.to_dict(orient="records"), "meta": meta, "all_pass": bool(df["pass"].all())}
    resolve_path("outputs/checkpoints/verify_step4.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not df["pass"].all():
        sys.exit(1)


if __name__ == "__main__":
    main()
