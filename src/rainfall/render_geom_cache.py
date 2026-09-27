"""Serialize render geometry once; workers avoid GPKG/SQLite."""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path

from rainfall.config import load_config, resolve_path
from rainfall.frozen_layout import render_config_hash
from rainfall.render_geom import RenderGeometry, load_render_geometry


def geom_cache_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    h = render_config_hash(cfg)
    return resolve_path(f"outputs/render_cache/{h}/geometry.pkl")


def ensure_geometry_cache(cfg: dict | None = None, force: bool = False) -> Path:
    path = geom_cache_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return path
    geom = load_render_geometry(cfg, use_cache=False)
    with path.open("wb") as f:
        pickle.dump(geom, f, protocol=pickle.HIGHEST_PROTOCOL)
    meta = {"hash": render_config_hash(cfg), "path": str(path), "size_bytes": path.stat().st_size}
    path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path


def load_geometry_cached(cfg: dict | None = None) -> RenderGeometry:
    path = ensure_geometry_cache(cfg)
    with path.open("rb") as f:
        return pickle.load(f)
