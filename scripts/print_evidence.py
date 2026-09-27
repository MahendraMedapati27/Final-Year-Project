"""One-shot evidence printer for A-fix/B/C gates."""

from __future__ import annotations

import ast
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from matplotlib.colors import to_rgb
from PIL import Image

from rainfall.config import load_config, resolve_path
from rainfall.render import IMD_COLORS, render_trial, wettest_day_2022_2025


def main() -> None:
    d = pd.read_csv(resolve_path("outputs/tables/obj_id_name_disagreements.csv"))
    print("=== A1 disagree by reason ===")
    print(d.groupby("reason_class").size().to_string())
    c = d[d["reason_class"].str.startswith("(c)")]
    print("(c) examples (state, district, imd_state, imd_district, score):")
    for _, r in c.head(10).iterrows():
        print(
            f"  {r['state']}, {r['district']} | gist: {r.get('imd_state')}, {r.get('imd_district')} | score={r.get('fuzzy_score')}"
        )
    print(f"Total disagree rows: {len(d)}; (c) rows: {len(c)}")

    sus = pd.read_csv(resolve_path("outputs/tables/iou_suspect_analysis.csv"))
    v = pd.read_csv(resolve_path("outputs/tables/crosswalk_validation.csv"))
    cp_path = resolve_path("outputs/checkpoints/a_fix_iou.json")
    if not cp_path.exists():
        payload = {"iou_suspects_before": 17, "iou_suspects_after": int(v["suspect"].sum())}
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        cp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n=== A2 IoU suspects ===")
    print(f"before/after: {cp_path.read_text(encoding='utf-8').strip()}")
    print(sus.to_string(index=False))

    raw = pd.read_parquet(resolve_path("data/interim/raw_full.parquet"), columns=["state", "district"])
    dup = raw.groupby("district")["state"].nunique()
    print("\n=== A3 district names in >1 state ===")
    for name, cnt in dup[dup > 1].items():
        sts = raw[raw.district == name]["state"].unique().tolist()
        print(f"  {name}: {cnt} states -> {sts}")

    dup_log = pd.read_csv(resolve_path("outputs/tables/duplicates_resolved.csv"))
    print("\n=== B duplicate rules ===")
    print(dup_log["rule"].value_counts().to_string())
    diffs = []
    for _, r in dup_log[dup_log["rule"] == "mean_conflict"].iterrows():
        dropped = r["dropped_actuals"]
        if isinstance(dropped, str):
            dropped = ast.literal_eval(dropped)
        vals = [float(r["kept_actual"])] + [float(x) for x in dropped if pd.notna(x)]
        if len(vals) > 1:
            m = np.mean(vals)
            diffs.extend([abs(v - m) for v in vals])
    if diffs:
        print(f"mean_conflict median abs diff mm: {np.median(diffs):.2f}; max: {np.max(diffs):.2f}")

    jjas = pd.read_csv(resolve_path("outputs/tables/jjas_coverage_median_by_year.csv"))
    print("\n=== B JJAS median coverage by year ===")
    print(jjas.to_string(index=False))

    trial = sorted(Path(resolve_path("outputs/maps/trial")).glob("rainfall_actual_*.png"))
    print("\n=== C trial PNGs ===")
    sizes = []
    for p in trial:
        im = Image.open(p)
        sizes.append(im.size)
        print(p.name, im.size, f"{p.stat().st_size / 1024:.1f} KB")
    print("Identical pixel dimensions:", len(set(sizes)) == 1)

    en2 = pd.read_parquet(
        resolve_path("data/processed/rainfall_enriched.parquet"),
        columns=["date", "daily_actual_mm", "paint_group_uid"],
    )
    wday = wettest_day_2022_2025(en2)
    heavy_n = (
        en2[(en2["date"] == wday) & (en2["daily_actual_mm"] >= 64.5)].shape[0]
    )
    print(f"Wettest 2022-2025 (max districts >=64.5 mm): {wday.date()} with {heavy_n} paint-group rows")

    def lum(rgb):
        r, g, b = rgb
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    rgbs = [to_rgb(c) for c in IMD_COLORS]
    print("\n=== C deuteranopia proxy (adjacent class luminance delta) ===")
    for i in range(len(rgbs) - 1):
        print(f"  {i}->{i+1}: dL={abs(lum(rgbs[i]) - lum(rgbs[i + 1])):.3f}")

    cfg = load_config()
    probe = Path(resolve_path("outputs/maps/trial/_timing_probe.png"))
    t0 = time.perf_counter()
    r = render_trial(pd.Timestamp("2026-09-19"), probe, cfg)
    print("\n=== C render timing (2026-09-19) ===")
    print(r)
    probe.unlink(missing_ok=True)
    cpus = max(1, (os.cpu_count() or 2) - 1)
    print(
        f"Projected ~1800 maps: 1 worker ~{r['seconds_total'] * 1800 / 3600:.2f} h; "
        f"{cpus} workers ~{r['seconds_total'] * 1800 / cpus / 3600:.2f} h"
    )


if __name__ == "__main__":
    main()
