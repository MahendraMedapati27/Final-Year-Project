"""STEP 1: PNG provenance, PIL decode all, archive render_errors."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from rainfall.config import resolve_path


def _mtime(p: Path) -> float | None:
    return p.stat().st_mtime if p.exists() else None


def _git_last(path: str) -> str | None:
    import subprocess

    try:
        r = subprocess.run(
            ["git", "log", "-1", "--format=%ci", "--", path],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(resolve_path(".")),
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


def main() -> None:
    maps_root = resolve_path("outputs/maps/daily_actual")
    pngs = sorted(maps_root.rglob("rainfall_actual_*.png"))
    mtimes = [p.stat().st_mtime for p in pngs]
    if not mtimes:
        print("png_count 0")
        return
    tmin = datetime.fromtimestamp(min(mtimes), tz=timezone.utc)
    tmax = datetime.fromtimestamp(max(mtimes), tz=timezone.utc)
    print("png_count", len(pngs))
    print("mtime_utc_min", tmin.isoformat())
    print("mtime_utc_max", tmax.isoformat())

    inputs: dict[str, Path] = {
        "render_matrix.npz": resolve_path("data/processed/render_matrix.npz"),
        "geometry.pkl": resolve_path("outputs/render_cache/df830c365182acaf/geometry.pkl"),
        "config.yaml": resolve_path("config/config.yaml"),
        "palette_lab.py": resolve_path("src/rainfall/palette_lab.py"),
        "render_engine.py": resolve_path("src/rainfall/render_engine.py"),
        "render_layout.py": resolve_path("src/rainfall/render_layout.py"),
        "render_daily.py": resolve_path("src/rainfall/render_daily.py"),
    }
    # discover geometry.pkl if hash dir differs
    cache_root = resolve_path("outputs/render_cache")
    if cache_root.exists():
        pkls = list(cache_root.rglob("geometry.pkl"))
        if pkls:
            inputs["geometry.pkl"] = max(pkls, key=lambda p: p.stat().st_mtime)

    thresholds: dict[str, float] = {}
    print("\ninput_change_times:")
    for name, path in inputs.items():
        git_t = _git_last(str(path.relative_to(resolve_path("."))) if path.is_relative_to(resolve_path(".")) else str(path))
        m = _mtime(path)
        iso = datetime.fromtimestamp(m, tz=timezone.utc).isoformat() if m else "missing"
        print(f"  {name}: file_mtime_utc={iso} git_last={git_t or 'n/a'}")
        if m:
            thresholds[name] = m

    design_cutoff = max(thresholds.values())
    cutoff_iso = datetime.fromtimestamp(design_cutoff, tz=timezone.utc).isoformat()
    print("\ndesign_cutoff_utc", cutoff_iso)

    before_after: dict[str, int] = {}
    for name, thr in thresholds.items():
        before = sum(1 for t in mtimes if t < thr)
        after = len(mtimes) - before
        before_after[name] = before
        print(f"png_before_{name}", before, "png_after", after)

    stale = sum(1 for t in mtimes if t < design_cutoff)
    print("stale_suspects_vs_design_cutoff", stale)

    by_month: dict[str, int] = {}
    for p in pngs:
        key = p.parent.parent.name + "-" + p.parent.name
        by_month[key] = by_month.get(key, 0) + 1
    print("\npng_count_by_yyyy_mm (first 12 / last 12 keys):")
    keys = sorted(by_month.keys())
    for k in keys[:12]:
        print(f"  {k}: {by_month[k]}")
    if len(keys) > 24:
        print("  ...")
    for k in keys[-12:]:
        print(f"  {k}: {by_month[k]}")

    err = resolve_path("logs/render_errors.csv")
    hist = resolve_path("logs/render_errors_history.csv")
    if err.exists():
        if hist.exists():
            with hist.open("a", encoding="utf-8") as h, err.open(encoding="utf-8") as e:
                body = e.read()
                if body.strip():
                    h.write(f"\n# archived {datetime.now(timezone.utc).isoformat()}\n")
                    h.write(body)
        else:
            shutil.copy2(err, hist)
        print("\narchived render_errors ->", hist)

    decode_fail: list[str] = []
    for i, p in enumerate(pngs):
        try:
            with Image.open(p) as im:
                im.load()
        except Exception as e:
            decode_fail.append(f"{p}:{e}")
        if (i + 1) % 400 == 0:
            print(f"pil_decode_progress {i+1}/{len(pngs)}", flush=True)
    print("pil_decode_failures", len(decode_fail))
    if decode_fail[:5]:
        for line in decode_fail[:5]:
            print(" ", line)

    out = {
        "png_count": len(pngs),
        "mtime_utc_min": tmin.isoformat(),
        "mtime_utc_max": tmax.isoformat(),
        "design_cutoff_utc": cutoff_iso,
        "stale_suspects": stale,
        "pil_decode_failures": len(decode_fail),
        "before_after": before_after,
    }
    resolve_path("outputs/checkpoints/verify_step1.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
