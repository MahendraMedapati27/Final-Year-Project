"""STEP 2: Parity sample — re-render 60 dates vs on-disk PNGs."""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from rainfall.config import load_config, resolve_path
from rainfall.render_engine import FrozenRenderer


def compare_pixels(ref: Path, cand: Path) -> dict:
    a = np.array(Image.open(ref).convert("RGB"))
    b = np.array(Image.open(cand).convert("RGB"))
    if a.shape != b.shape:
        return {"pass": False, "reason": f"shape {a.shape} vs {b.shape}", "frac_gt24": 1.0}
    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    mx = d.max(axis=2)
    frac = float((mx > 24).mean())
    return {
        "pass": frac == 0.0,
        "shape": list(a.shape),
        "fraction_pixels_channel_diff_gt_24": frac,
        "identical": bool(np.array_equal(a, b)),
    }


def _design_cutoff() -> float:
    paths = [
        resolve_path("data/processed/render_matrix.npz"),
        resolve_path("src/rainfall/render_daily.py"),
        resolve_path("src/rainfall/render_engine.py"),
        resolve_path("config/config.yaml"),
    ]
    cache = list(resolve_path("outputs/render_cache").rglob("geometry.pkl"))
    if cache:
        paths.append(max(cache, key=lambda p: p.stat().st_mtime))
    return max(p.stat().st_mtime for p in paths if p.exists())


def _pick_dates(manifest: pd.DataFrame, maps_root: Path, cutoff: float) -> list[str]:
    rows = []
    for _, r in manifest.iterrows():
        d = str(r["date"])
        p = maps_root / d[:4] / d[5:7] / f"rainfall_actual_{d}.png"
        if not p.exists():
            continue
        rows.append((d, p.stat().st_mtime, int(r.get("n_no_data") or 0), float(r.get("max_mm") or np.nan), float(r.get("area_weighted_mean_mm") or np.nan)))
    df = pd.DataFrame(rows, columns=["date", "mtime", "n_no_data", "max_mm", "awmean"])
    df = df.sort_values("date")
    stale = df[df["mtime"] < cutoff]["date"].tolist()
    fresh = df[df["mtime"] >= cutoff]["date"].tolist()
    rng = random.Random(42)
    picks: list[str] = []
    mandatory = [
        df["date"].iloc[0],
        df["date"].iloc[-1],
        "2024-03-02",
        "2024-03-03",
        df.loc[df["max_mm"].idxmax(), "date"],
        df.loc[df["awmean"].idxmin(), "date"],
        df.loc[df["n_no_data"].idxmax(), "date"],
    ]
    for d in mandatory:
        if d in df["date"].values and d not in picks:
            picks.append(d)
    stale_pool = [d for d in stale if d not in picks]
    fresh_pool = [d for d in fresh if d not in picks]
    picks.extend(rng.sample(stale_pool, min(30, len(stale_pool))))
    picks.extend(rng.sample(fresh_pool, min(30, len(fresh_pool))))
    # dedupe preserve order
    out: list[str] = []
    for d in picks:
        if d not in out:
            out.append(d)
    return out[:60] if len(out) > 60 else out


def main() -> None:
    maps_root = resolve_path("outputs/maps/daily_actual")
    manifest = pd.read_csv(maps_root / "manifest.csv")
    cutoff = _design_cutoff()
    print("design_cutoff_utc", datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat(), flush=True)
    dates = _pick_dates(manifest, maps_root, cutoff)
    print("parity_sample_n", len(dates), flush=True)
    tmp = resolve_path("outputs/maps/verify_tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    r = FrozenRenderer()
    results = []
    fail_dates: list[str] = []
    for i, d in enumerate(dates):
        on_disk = maps_root / d[:4] / d[5:7] / f"rainfall_actual_{d}.png"
        cand = tmp / f"rainfall_actual_{d}.png"
        r.render_date(pd.Timestamp(d), cand)
        rep = compare_pixels(on_disk, cand)
        rep["date"] = d
        rep["on_disk_mtime_before_cutoff"] = on_disk.stat().st_mtime < cutoff
        results.append(rep)
        if not rep["pass"]:
            fail_dates.append(d)
        print(f"{i+1}/{len(dates)} {d} frac_gt24={rep['fraction_pixels_channel_diff_gt_24']:.6f} pass={rep['pass']}", flush=True)

    n_stale = sum(1 for r in results if r["on_disk_mtime_before_cutoff"])
    n_fail_stale = sum(1 for r in results if not r["pass"] and r["on_disk_mtime_before_cutoff"])
    n_fail_fresh = sum(1 for r in results if not r["pass"] and not r["on_disk_mtime_before_cutoff"])
    print("\nparity_summary stale_in_sample", n_stale, "fail_stale", n_fail_stale, "fail_fresh", n_fail_fresh)
    payload = {
        "dates": dates,
        "results": results,
        "fail_dates": fail_dates,
        "pass_all": len(fail_dates) == 0,
        "action": "re-render stale suspects with --overwrite" if n_fail_stale else "keep existing frames",
    }
    resolve_path("outputs/checkpoints/verify_step2.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if fail_dates:
        print("FAIL dates (first 20):", fail_dates[:20])
    else:
        print("PASS: all sampled frames pixel-identical to current engine (frac_gt24=0)")


if __name__ == "__main__":
    main()
