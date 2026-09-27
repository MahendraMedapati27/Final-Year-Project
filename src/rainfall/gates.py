"""Print Part A/B/C gate tables from on-disk evidence (runs checks where needed)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from rainfall.config import load_config, resolve_path


def checkpoint(name: str, payload: dict) -> Path:
    p = resolve_path(f"outputs/checkpoints/{name}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return p


def print_part_a_gate() -> dict:
    from rainfall.a_fix import measure_render_seconds, print_part_a_gate as _gate

    v = pd.read_csv(resolve_path("outputs/tables/crosswalk_validation.csv"))
    disagree = pd.read_csv(resolve_path("outputs/tables/obj_id_name_disagreements.csv"))
    agree = pd.read_csv(resolve_path("outputs/tables/obj_id_name_agreement.csv"))
    poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    out = {
        "name_agreement_pct": float(agree["agrees"].mean() * 100),
        "n_disagree": len(disagree),
        "n_disagree_c": int(disagree["reason_class"].str.startswith("(c)").sum()),
        "iou_median": float(v["iou"].median()),
        "iou_suspects": int(v["suspect"].sum()),
        "resolution_counts": poly["resolution"].value_counts().to_dict(),
    }
    _gate()
    sec = measure_render_seconds()
    out["render_draw_seconds_785_150dpi"] = sec
    checkpoint("part_a_gate", out)
    return out


def print_part_b_gate() -> dict:
    cfg = load_config()
    raw_path = resolve_path("data/interim/raw_full.parquet")
    en_path = resolve_path(cfg["paths"]["processed_enriched"])
    ded_path = resolve_path("data/processed/checkpoints/deduped.parquet")

    n_raw = pd.read_parquet(raw_path, columns=["date"]).shape[0] if raw_path.exists() else None
    n_ded = pd.read_parquet(ded_path, columns=["date"]).shape[0] if ded_path.exists() else None
    n_en = pd.read_parquet(en_path, columns=["date"]).shape[0] if en_path.exists() else None

    dup = pd.read_csv(resolve_path("outputs/tables/duplicates_resolved.csv"))
    rules = dup["rule"].value_counts().to_dict() if "rule" in dup.columns else {}
    import ast

    conflicts = dup[dup["rule"] == "mean_conflict"] if "rule" in dup.columns else pd.DataFrame()
    conf_diffs = []
    if len(conflicts):
        for _, r in conflicts.iterrows():
            dropped = r["dropped_actuals"]
            if isinstance(dropped, str):
                dropped = ast.literal_eval(dropped)
            vals = [float(r["kept_actual"])] + [float(x) for x in dropped if pd.notna(x)]
            if len(vals) > 1:
                m = np.mean(vals)
                conf_diffs.extend([abs(v - m) for v in vals])

    dates = pd.date_range("2021-01-01", "2026-09-19", freq="D")
    en_dates = pd.read_parquet(en_path, columns=["date"])["date"].unique()
    n_cal, n_present, n_missing = len(dates), len(en_dates), len(dates) - len(en_dates)

    mem_lines = []
    mem_path = resolve_path("logs/clean_memory.jsonl")
    if mem_path.exists():
        mem_lines = mem_path.read_text(encoding="utf-8").strip().splitlines()
    peak_rss = max(
        (json.loads(l).get("rss_mb", 0) for l in mem_lines if l.strip()),
        default=0.0,
    )
    blow_step = None
    for l in mem_lines:
        rec = json.loads(l)
        if rec.get("rss_mb", 0) > 1500:
            blow_step = rec.get("step")

    miss = pd.read_csv(resolve_path("outputs/tables/missing_days_by_month.csv")) if Path(
        resolve_path("outputs/tables/missing_days_by_month.csv")
    ).exists() else None

    import pyarrow.parquet as pq

    schema_names = pq.read_schema(en_path).names if en_path.exists() else []
    qc_cols = [c for c in schema_names if c.startswith("qc_")]
    sample_cols = [
        "date",
        "state",
        "district",
        "daily_actual_mm",
        "daily_departure_pct",
        "paint_group_uid",
        "monsoon_cum_mm",
        "monsoon_cum_complete",
    ]
    en = pd.read_parquet(en_path, columns=[c for c in sample_cols if c in schema_names])

    vijay = en[(en["state"] == "Karnataka") & (en["district"] == "Vijayapura")].head(5)
    jk = en[en["state"].astype(str).str.contains("Jammu", na=False)].head(5)

    print("\n=== PART B GATE ===")
    print(f"Raw rows: {n_raw:,}; deduped: {n_ded:,}; enriched: {n_en:,}")
    print(f"Calendar: {n_cal} days; present: {n_present}; missing: {n_missing}")
    print(f"Dup groups resolved: {len(dup):,}; rules: {rules}")
    if conf_diffs:
        print(f"mean_conflict median abs diff mm: {np.median(conf_diffs):.2f}; max: {np.max(conf_diffs):.2f}")
    else:
        print("mean_conflict diffs: not run")
    print(f"QC columns in enriched: {len(qc_cols)} ({qc_cols[:5]}...)")
    print(f"Peak RSS from clean_memory.jsonl: {peak_rss:.1f} MB; highest step: {blow_step}")
    print("Vijayapura head:\n", vijay.to_string(index=False))
    print("J&K head:\n", jk.to_string(index=False))

    gate_path = resolve_path("logs/m3_gate.json")
    wall = json.loads(gate_path.read_text())["wall_s"] if gate_path.exists() else None
    out = {
        "n_raw": n_raw,
        "n_deduped": n_ded,
        "n_enriched": n_en,
        "calendar_days": n_cal,
        "dates_present": n_present,
        "dates_missing": n_missing,
        "dup_rules": rules,
        "peak_rss_mb": peak_rss,
        "blow_step": blow_step,
        "wall_s_last_gate_json": wall,
    }
    checkpoint("part_b_gate", out)
    return out


def print_part_c_gate() -> dict:
    from PIL import Image

    trial = resolve_path("outputs/maps/trial")
    paths = sorted(trial.glob("rainfall_actual_*.png"))
    rows = []
    for p in paths:
        im = Image.open(p)
        rows.append({"path": str(p), "size": im.size, "kb": p.stat().st_size / 1024})
    npz = resolve_path("data/processed/render_matrix.npz")
    npz_info = {}
    if npz.exists():
        z = np.load(npz)
        npz_info = {"dates": len(z["dates"]), "polygons": z["values"].shape[1], "dtype": str(z["values"].dtype)}

    print("\n=== PART C GATE ===")
    for r in rows:
        print(r)
    print("render_matrix.npz:", npz_info or "not run")
    out = {"maps": rows, "npz": npz_info}
    checkpoint("part_c_gate", out)
    return out
