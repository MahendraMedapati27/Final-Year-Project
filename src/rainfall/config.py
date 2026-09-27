"""Load project configuration from config/config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PKG_ROOT = Path(__file__).resolve().parents[2]


def project_root() -> Path:
    """Repository root (parent of src/)."""
    return _PKG_ROOT


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or (_PKG_ROOT / "config" / "config.yaml")
    with path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg


def resolve_path(relative: str, root: Path | None = None) -> Path:
    base = root or project_root()
    return (base / relative).resolve()


def raw_csv_path(cfg: dict[str, Any], sample: bool) -> Path:
    key = "raw_csv_sample" if sample else "raw_csv_full"
    return resolve_path(cfg["paths"][key])


def interim_parquet_path(cfg: dict[str, Any]) -> Path:
    return resolve_path(cfg["paths"]["interim_parquet"])
