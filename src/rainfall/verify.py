"""Verify enriched parquet against PROMPT section 6."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from rainfall.config import load_config, resolve_path
from rainfall.schema import SECTION_6_COLUMNS, all_section6_columns


def schema_checklist(path: Path) -> pd.DataFrame:
    schema = pq.read_schema(path)
    names = set(schema.names)
    n = pq.read_metadata(path).num_rows
    rows = []
    pf = pq.ParquetFile(path)
    for section, cols in SECTION_6_COLUMNS.items():
        for col in cols:
            present = col in names
            dtype = str(schema.field(col).type) if present else ""
            null_pct = np.nan
            if present:
                s = pf.read(columns=[col]).to_pandas()[col]
                null_pct = float(s.isna().mean() * 100)
                del s
            rows.append({"section": section, "column": col, "present": present, "dtype": dtype, "null_pct": null_pct})
    out = pd.DataFrame(rows)
    out.to_csv(resolve_path("outputs/tables/schema_checklist.csv"), index=False)
    return out


def run_verify(sample: bool = False) -> dict:
    cfg = load_config()
    raw_path = resolve_path("data/interim/raw_sample.parquet" if sample else "data/interim/raw_full.parquet")
    en_path = resolve_path(cfg["paths"]["processed_enriched"])
    dup_path = resolve_path("outputs/tables/duplicates_resolved.csv")

    n_raw = pq.read_metadata(raw_path).num_rows
    n_en = pq.read_metadata(en_path).num_rows
    dup_log = pd.read_csv(dup_path)
    n_groups = len(dup_log)
    if "n_in_group" in dup_log.columns:
        n_removed = int((dup_log["n_in_group"] - 1).sum())
    else:
        n_removed = n_groups

    df = pd.read_parquet(en_path, columns=["district_uid", "date", "daily_actual_mm"])
    dup_keys = df.duplicated(subset=["district_uid", "date"]).sum()
    neg = (df["daily_actual_mm"] < 0).sum()

    expected = n_raw - n_removed
    row_ok = n_en == expected

    checklist = schema_checklist(en_path)
    missing = checklist[~checklist["present"]]["column"].tolist()

    result = {
        "n_raw": int(n_raw),
        "n_enriched": int(n_en),
        "n_dup_groups": int(n_groups),
        "n_rows_removed_in_dedupe": int(n_removed),
        "expected_rows": int(expected),
        "row_count_ok": bool(row_ok),
        "district_uid_date_unique": bool(int(dup_keys) == 0),
        "negative_rainfall_rows": int(neg),
        "missing_section6_columns": missing,
        "all_section6_present": bool(len(missing) == 0),
        "ok": bool(row_ok and dup_keys == 0 and neg == 0 and len(missing) == 0),
    }
    out = resolve_path("outputs/checkpoints/verify.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
