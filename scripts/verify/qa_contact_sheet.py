"""Build QA contact sheet from manifest + enriched dates."""

from __future__ import annotations

import random
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

from rainfall.config import resolve_path


def _special_dates(en: pd.DataFrame, missing: list[pd.Timestamp]) -> list[pd.Timestamp]:
    en = en.copy()
    en["date"] = pd.to_datetime(en["date"])
    ac = "daily_actual_mm_map"
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


def main() -> None:
    maps_root = resolve_path("outputs/maps/daily_actual")
    manifest_path = maps_root / "manifest.csv"
    if not manifest_path.exists():
        raise SystemExit("manifest.csv missing — run full render first")
    manifest = pd.read_csv(manifest_path)
    en = pd.read_parquet(resolve_path("data/processed/rainfall_enriched.parquet"), columns=["date", "daily_actual_mm_map"])
    en["date"] = pd.to_datetime(en["date"])
    all_dates = sorted(en["date"].unique())
    cal = pd.date_range(all_dates[0], all_dates[-1], freq="D")
    missing = [d for d in cal if d not in set(all_dates)]
    rng = random.Random(42)
    all_d = manifest["date"].astype(str).tolist()
    specials = [str(d.date()) for d in _special_dates(en, missing)]
    pool = list(dict.fromkeys(specials + rng.sample(all_d, min(24, len(all_d)))))
    imgs: list[tuple[str, Image.Image]] = []
    for d in pool:
        p = maps_root / d[:4] / d[5:7] / f"rainfall_actual_{d}.png"
        if p.exists():
            imgs.append((d, Image.open(p)))
    cols = 6
    rows = int(np.ceil(len(imgs) / cols)) or 1
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.5, rows * 2.8))
    axes = np.atleast_2d(axes)
    for ax in axes.flat:
        ax.axis("off")
    for i, (d, im) in enumerate(imgs):
        r, c = divmod(i, cols)
        axes[r, c].imshow(im)
        axes[r, c].set_title(d, fontsize=7)
    out = resolve_path("outputs/figures/qa_contact_sheet.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=120, facecolor="white")
    plt.close(fig)
    print("wrote", out, "n_panels", len(imgs))


if __name__ == "__main__":
    main()
