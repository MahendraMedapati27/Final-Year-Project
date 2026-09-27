"""STEP 2: parity vs approved reference PNGs."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from rainfall.config import resolve_path
from rainfall.render_engine import FrozenRenderer


def compare(ref: Path, cand: Path, diff_out: Path) -> dict:
    a = np.array(Image.open(ref).convert("RGB"))
    b = np.array(Image.open(cand).convert("RGB"))
    assert a.shape == b.shape
    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    mx = d.max(axis=2)
    frac_gt24 = float((mx > 24).mean())
    border = np.zeros(mx.shape, bool)
    border[1:-1, 1:-1] = mx[1:-1, 1:-1] > 24
    border |= (mx > 24) & (
        (np.roll(mx, 1, 0) > 24) | (np.roll(mx, -1, 0) > 24) | (np.roll(mx, 1, 1) > 24) | (np.roll(mx, -1, 1) > 24)
    )
    diff_img = np.zeros((*mx.shape, 3), dtype=np.uint8)
    diff_img[mx > 24] = [255, 0, 0]
    Image.fromarray(diff_img).save(diff_out)
    return {
        "shape": list(a.shape),
        "fraction_pixels_channel_diff_gt_24": frac_gt24,
        "identical": bool(np.array_equal(a, b)),
    }


def main() -> None:
    out_dir = resolve_path("outputs/maps/p3_parity")
    out_dir.mkdir(parents=True, exist_ok=True)
    refs = {
        "2026-09-19": resolve_path("outputs/maps/reference/approved_2026-09-19.png"),
        "2021-01-31": resolve_path("outputs/maps/reference/approved_2021-01-31.png"),
    }
    r = FrozenRenderer()
    rows = []
    for d, ref in refs.items():
        cand = out_dir / f"rainfall_actual_{d}.png"
        r.render_date(__import__("pandas").Timestamp(d), cand)
        rep = compare(ref, cand, out_dir / f"diff_{d}.png")
        rep["date"] = d
        rows.append(rep)
        print(d, rep)
    payload = {"engine": "legacy_frozen_pillow", "comparisons": rows, "pass": all(r["fraction_pixels_channel_diff_gt_24"] < 0.015 for r in rows)}
    resolve_path("outputs/checkpoints/p3_parity.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
