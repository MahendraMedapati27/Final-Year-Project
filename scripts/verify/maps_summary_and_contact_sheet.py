"""STEP 5: Contact sheet + maps_summary_by_year.csv + JJAS coverage."""

from __future__ import annotations

import random
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

from rainfall.config import resolve_path
from rainfall.jjas_sanity import jjas_coverage_by_year


def _missing_gap_dates(all_dates: set[pd.Timestamp], cal: pd.DatetimeIndex) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    missing = [d for d in cal if d not in all_dates]
    if not missing:
        return None, None
    g0 = missing[0]
    return g0 - pd.Timedelta(days=1), g0 + pd.Timedelta(days=1)


def main() -> None:
    maps_root = resolve_path("outputs/maps/daily_actual")
    man = pd.read_csv(maps_root / "manifest.csv")
    en_path = resolve_path("data/processed/rainfall_enriched.parquet")
    en = pd.read_parquet(en_path, columns=["date", "daily_actual_mm_map", "state_std", "district_std"])
    en["date"] = pd.to_datetime(en["date"])
    all_dates = set(en["date"])
    cal = pd.date_range(en["date"].min(), en["date"].max(), freq="D")
    missing_n = len([d for d in cal if d not in all_dates])
    gb, ga = _missing_gap_dates(all_dates, cal)

    by_day = en.groupby("date", observed=True)["daily_actual_mm_map"]
    aw = man.set_index("date")["area_weighted_mean_mm"]
    rows = []
    for y, g in man.groupby(man["date"].str[:4].astype(int)):
        dates_y = g["date"].astype(str).tolist()
        miss_y = sum(1 for d in pd.date_range(f"{y}-01-01", f"{y}-12-31", freq="D") if pd.Timestamp(d) not in all_dates)
        heavy = int((g["n_heavy"] > 0).sum()) if "n_heavy" in g.columns else 0
        idx = g["max_mm"].idxmax()
        rmax = g.loc[idx]
        rows.append(
            {
                "year": y,
                "n_dates_with_data": len(g),
                "missing_days_in_year": miss_y,
                "mean_of_daily_area_weighted_mean_mm": float(g["area_weighted_mean_mm"].mean()),
                "days_with_any_district_ge_64_5mm": heavy,
                "max_district_day_mm": float(rmax["max_mm"]),
                "max_district": rmax.get("wettest_district"),
                "max_date": rmax["date"],
            }
        )
    summary = pd.DataFrame(rows).sort_values("year")
    out_csv = resolve_path("outputs/tables/maps_summary_by_year.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_csv, index=False)
    print(summary.to_string(index=False))
    print("\nmissing_days_in_full_span", missing_n)
    try:
        jjas = jjas_coverage_by_year()
        print("\nJJAS coverage by year:")
        print(jjas.to_string(index=False))
    except Exception as e:
        print("JJAS coverage: not run", e)

    # contact sheet
    wet_d = str(man.loc[man["max_mm"].idxmax(), "date"])
    dry_d = str(man.loc[man["area_weighted_mean_mm"].idxmin(), "date"])
    nd_d = str(man.loc[man["n_no_data"].idxmax(), "date"])
    first_d = str(man["date"].min())
    last_d = str(man["date"].max())
    specials = [first_d, last_d, wet_d, dry_d, nd_d]
    if gb is not None:
        specials.append(str(gb.date()))
    if ga is not None:
        specials.append(str(ga.date()))
    rng = random.Random(42)
    pool = man["date"].astype(str).tolist()
    picks = list(dict.fromkeys(specials + rng.sample(pool, min(24, len(pool)))))
    imgs = []
    for d in picks:
        p = maps_root / d[:4] / d[5:7] / f"rainfall_actual_{d}.png"
        if p.exists():
            imgs.append((d, Image.open(p)))
    cols = 6
    rows_n = int(np.ceil(len(imgs) / cols)) or 1
    fig, axes = plt.subplots(rows_n, cols, figsize=(cols * 2.5, rows_n * 2.8))
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
    print("\nwrote", out, "panels", len(imgs))


if __name__ == "__main__":
    main()
