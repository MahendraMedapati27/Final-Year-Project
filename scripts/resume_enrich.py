"""Resume enrich + finalize from deduped checkpoint (P1 recovery)."""

from __future__ import annotations

import json
import time

import pandas as pd

from rainfall.config import resolve_path
from rainfall.m3_clean import _write_enriched_parquet, enrich_dataframe
from rainfall.m3_finalize import run_finalize
from rainfall.memory_log import log_step, rss_mb


def main() -> None:
    t0 = time.perf_counter()
    ded = pd.read_parquet(resolve_path("data/processed/checkpoints/deduped.parquet"))
    cw = pd.read_csv(resolve_path("data/processed/district_crosswalk.csv"))
    pg = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    log_step("enrich_resume", {"rows": len(ded)})
    en = enrich_dataframe(ded, cw, pg)
    out = resolve_path("data/processed/rainfall_enriched.parquet")
    _write_enriched_parquet(en, out)
    run_finalize()
    manifest = {
        "stage": "enrich_resume",
        "n_enriched": len(en),
        "wall_s": time.perf_counter() - t0,
        "peak_rss_mb": rss_mb(),
        "outputs": {"enriched": str(out)},
    }
    resolve_path("logs/run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    resolve_path("outputs/checkpoints/p1_clean.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(manifest)


if __name__ == "__main__":
    main()
