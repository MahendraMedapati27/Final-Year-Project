"""Light QA dry-run (file/manifest only, no matplotlib)."""

from __future__ import annotations

import pandas as pd
from PIL import Image

from rainfall.config import resolve_path


def main() -> None:
    root = resolve_path("outputs/maps/daily_actual")
    pngs = sorted(root.rglob("rainfall_actual_*.png"))
    en = pd.read_parquet(resolve_path("data/processed/rainfall_enriched.parquet"), columns=["date"])
    n = int(en["date"].nunique())
    sizes = {Image.open(p).size for p in pngs[: min(40, len(pngs))]}
    print("png_count", len(pngs), "expected", n)
    print("zero_byte", sum(1 for p in pngs if p.stat().st_size == 0))
    print("dimension_sample", sizes)
    man = root / "manifest.csv"
    if man.exists():
        print("manifest_rows", len(pd.read_csv(man)))


if __name__ == "__main__":
    main()
