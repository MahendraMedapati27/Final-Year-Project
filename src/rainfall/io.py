"""Raw CSV ingestion and Parquet conversion."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
from rainfall.config import interim_parquet_path, load_config, project_root, raw_csv_path, resolve_path

logger = logging.getLogger(__name__)

# Expected logical columns after rename (25 source columns)
COLUMN_PATTERNS: list[tuple[str, str]] = [
    (r"^Country$", "country"),
    (r"^State$", "state"),
    (r"^District$", "district"),
    (r"^Year$", "year_label"),
    (r"^Calendar Day$", "calendar_day_raw"),
    (r"^Obj_Id$", "obj_id"),
    (r"^Daily Category$", "daily_category_provided"),
    (r"^Weekly Date$", "weekly_date_raw"),
    (r"^Weekly Category$", "weekly_category_provided"),
    (r"^Cumulative Date$", "cumulative_date_raw"),
    (r"^Cumulative Category$", "cumulative_category_provided"),
    (r"^Monthly Date$", "monthly_date_raw"),
    (r"^Monthly Category$", "monthly_category_provided"),
    (r"^Daily Actual", "daily_actual_mm"),
    (r"^Daily Normal", "daily_normal_mm"),
    (r"^Percentage Of Daily Departure", "daily_departure_pct_provided"),
    (r"^Weekly Actual", "weekly_actual_mm_provided"),
    (r"^Weekly Normal", "weekly_normal_mm_provided"),
    (r"^Percentage Of Weekly Departure", "weekly_departure_pct_provided"),
    (r"^Cumulative Actual", "cumulative_actual_mm_provided"),
    (r"^Cumulative Normal", "cumulative_normal_mm_provided"),
    (r"^Percentage Of Cumulative Departure", "cumulative_departure_pct_provided"),
    (r"^Monthly Acutual|^Monthly Actual", "monthly_actual_mm_provided"),
    (r"^Monthly Normal", "monthly_normal_mm_provided"),
    (r"^Percentage Of Monthly Departure", "monthly_departure_pct_provided"),
]

EXPECTED_N_COLS = 25


def map_raw_columns(raw_names: list[str]) -> dict[str, str]:
    """Map raw CSV header names to snake_case logical names by position + regex."""
    if len(raw_names) != EXPECTED_N_COLS:
        raise ValueError(f"Expected {EXPECTED_N_COLS} columns, got {len(raw_names)}")
    mapping: dict[str, str] = {}
    used_targets: set[str] = set()
    for i, raw in enumerate(raw_names):
        matched = False
        for pattern, target in COLUMN_PATTERNS:
            if re.search(pattern, raw, re.IGNORECASE):
                if target in used_targets:
                    raise ValueError(f"Duplicate target {target} for column {raw!r}")
                mapping[raw] = target
                used_targets.add(target)
                matched = True
                break
        if not matched:
            raise ValueError(f"No pattern for column index {i}: {raw!r}")
    if len(mapping) != EXPECTED_N_COLS:
        raise ValueError(f"Mapped {len(mapping)} columns, expected {EXPECTED_N_COLS}")
    return mapping


def read_raw_header(csv_path: Path) -> list[str]:
    df_head = pd.read_csv(csv_path, nrows=0)
    return list(df_head.columns)


def ingest_raw_csv(csv_path: Path) -> pd.DataFrame:
    """Read full CSV with pyarrow engine and apply column mapping."""
    logger.info("Reading %s", csv_path)
    raw_cols = read_raw_header(csv_path)
    col_map = map_raw_columns(raw_cols)
    logger.info("Column mapping verified (%d columns)", len(col_map))

    df = pd.read_csv(csv_path, engine="pyarrow")
    df = df.rename(columns=col_map)

    for cat_col in [
        "country",
        "state",
        "district",
        "year_label",
        "daily_category_provided",
        "weekly_category_provided",
        "cumulative_category_provided",
        "monthly_category_provided",
        "weekly_date_raw",
        "cumulative_date_raw",
        "monthly_date_raw",
    ]:
        if cat_col in df.columns:
            df[cat_col] = df[cat_col].astype("category")

    df["date"] = pd.to_datetime(df["calendar_day_raw"], errors="coerce")
    if df["obj_id"].notna().any():
        df["obj_id"] = pd.to_numeric(df["obj_id"], errors="coerce")

    for c in df.columns:
        if c.endswith("_mm") or c.endswith("_pct_provided"):
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")

    return df


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", compression="zstd", index=False)
    logger.info("Wrote parquet %s (%d rows)", path, len(df))


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def write_stage_manifest(
    stage: str,
    paths: dict[str, str],
    extra: dict[str, Any] | None = None,
    log_dir: Path | None = None,
) -> Path:
    log_dir = log_dir or (project_root() / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "stage": stage,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "paths": paths,
        "pandas": pd.__version__,
        "pyarrow": pa.__version__,
        "numpy": np.__version__,
    }
    if extra:
        manifest.update(extra)
    out = log_dir / f"{stage}_manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


def ingest_command(sample: bool, force: bool = False) -> Path:
    cfg = load_config()
    csv_path = raw_csv_path(cfg, sample=sample)
    parquet_path = interim_parquet_path(cfg)
    if not sample:
        parquet_path = parquet_path.parent / "raw_full.parquet"
    else:
        parquet_path = parquet_path.parent / "raw_sample.parquet"

    if parquet_path.exists() and not force:
        logger.info("Parquet exists, skipping ingest: %s", parquet_path)
        return parquet_path

    df = ingest_raw_csv(csv_path)
    write_parquet(df, parquet_path)
    write_stage_manifest(
        "ingest_sample" if sample else "ingest_full",
        {"csv": str(csv_path), "parquet": str(parquet_path)},
        extra={"n_rows": len(df), "csv_sha256": file_sha256(csv_path)},
    )
    return parquet_path


def load_parquet(sample: bool) -> pd.DataFrame:
    cfg = load_config()
    name = "raw_sample.parquet" if sample else "raw_full.parquet"
    path = resolve_path(cfg["paths"]["interim_parquet"]).parent / name
    if not path.exists():
        ingest_command(sample=sample, force=False)
    return pd.read_parquet(path)
