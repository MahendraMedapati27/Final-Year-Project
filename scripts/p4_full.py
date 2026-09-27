"""P4 full render + QA + contact sheet (stop on failure)."""

from __future__ import annotations

import json
import multiprocessing as mp
import random
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

from rainfall.config import resolve_path
from rainfall.render_batch import output_path, render_dates


def _special_dates(en: pd.DataFrame, missing: list[pd.Timestamp]) -> list[pd.Timestamp]:
    en = en.copy()
    en["date"] = pd.to_datetime(en["date"])
    ac = "daily_actual_mm_map" if "daily_actual_mm_map" in en.columns else "daily_actual_mm"
    by_day = en.groupby("date", observed=True)[ac].apply(lambda s: s.notna().sum())
    dates_sorted = sorted(en["date"].unique())
    first, last = pd.Timestamp(dates_sorted[0]), pd.Timestamp(dates_sorted[-1])
    wet = by_day.idxmax()
    dry = by_day.idxmin()
    most_nd = en.groupby("date", observed=True).apply(lambda g: g[ac].isna().sum(), include_groups=False).idxmax()
    gap_before = missing[0] - pd.Timedelta(days=1) if missing else None
    gap_after = missing[0] + pd.Timedelta(days=1) if missing else None
    picks = [first, last, pd.Timestamp(wet), pd.Timestamp(dry), pd.Timestamp(most_nd)]
    if gap_before is not None and gap_before in dates_sorted:
        picks.append(gap_before)
    if gap_after is not None and gap_after in dates_sorted:
        picks.append(gap_after)
    return picks


def contact_sheet(manifest: pd.DataFrame, en: pd.DataFrame, missing: list[pd.Timestamp], out: Path) -> None:
    rng = random.Random(42)
    all_d = manifest["date"].tolist()
    specials = [str(d.date()) for d in _special_dates(en, missing)]
    pool = list(dict.fromkeys(specials + rng.sample(all_d, min(24, len(all_d)))))
    imgs = []
    for d in pool[:30]:
        row = manifest[manifest["date"] == d]
        if row.empty:
            continue
        p = Path(row.iloc[0]["path"]) if "path" in row.columns else output_path(resolve_path("outputs/maps/daily_actual"), pd.Timestamp(d))
        if not p.exists():
            p = resolve_path(f"outputs/maps/daily_actual/{d[:4]}/{int(d[5:7]):02d}/rainfall_actual_{d}.png")
        if p.exists():
            imgs.append((d, Image.open(p)))
    if not imgs:
        return
    cols = 6
    rows = int(np.ceil(len(imgs) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.5, rows * 2.8))
    axes = np.atleast_2d(axes)
    for ax in axes.flat:
        ax.axis("off")
    for i, (d, im) in enumerate(imgs):
        r, c = divmod(i, cols)
        axes[r, c].imshow(im)
        axes[r, c].set_title(d, fontsize=7)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120, facecolor="white")
    plt.close(fig)


def qa_all(manifest: pd.DataFrame, maps_root: Path, n_data_dates: int) -> pd.DataFrame:
    pngs = sorted(maps_root.rglob("rainfall_actual_*.png"))
    checks = []
    checks.append(("file_count", len(pngs) == n_data_dates, len(pngs), n_data_dates))
    sizes = {Image.open(p).size for p in pngs[: min(50, len(pngs))]}
    checks.append(("identical_dimensions_sample", len(sizes) == 1, str(sizes), "one size"))
    err = resolve_path("logs/render_errors.csv")
    checks.append(("render_errors_empty", not err.exists() or err.stat().st_size == 0, 0, 0))
    if "n_districts_with_data" in manifest.columns and "legend" not in manifest.columns:
        checks.append(("manifest_has_rows", len(manifest) >= n_data_dates * 0.99, len(manifest), n_data_dates))
    return pd.DataFrame(checks, columns=["check", "pass", "got", "expected"])


def main() -> None:
    mp.freeze_support()
    en = pd.read_parquet(resolve_path("data/processed/rainfall_enriched.parquet"), columns=["date", "daily_actual_mm_map", "daily_actual_mm"])
    en["date"] = pd.to_datetime(en["date"])
    all_dates = sorted(en["date"].unique())
    cal = pd.date_range(all_dates[0], all_dates[-1], freq="D")
    missing = [d for d in cal if d not in set(all_dates)]
    pd.DataFrame({"missing_date": missing}).to_csv(resolve_path("outputs/maps/missing_dates.csv"), index=False)
    summary = render_dates([pd.Timestamp(d) for d in all_dates], overwrite=False, rebuild_matrix=False)
    manifest_path = resolve_path("outputs/maps/daily_actual/manifest.csv")
    manifest = pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame()
    qa = qa_all(manifest, resolve_path("outputs/maps/daily_actual"), len(all_dates))
    print(qa.to_string(index=False))
    contact_sheet(manifest, en, missing, resolve_path("outputs/figures/qa_contact_sheet.png"))
    payload = {
        "render": summary,
        "qa": qa.to_dict(orient="records"),
        "n_missing_calendar_dates": len(missing),
        "all_pass": bool(qa["pass"].all()),
    }
    resolve_path("outputs/checkpoints/p4_gate.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not qa["pass"].all():
        raise SystemExit("P4 QA failed — stopped before videos/analytics")


if __name__ == "__main__":
    main()
