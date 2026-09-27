"""Frozen layout constants (must match approved p2_trial PNGs). Do not change."""

from __future__ import annotations

import hashlib
import json

from rainfall.config import load_config
from rainfall.palette_lab import NODATA_FACE, OUTSIDE_FILL, PALETTE_HEX


def render_config_hash(cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    blob = json.dumps(cfg.get("render", {}), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def palette_rgb_uint8() -> "numpy.ndarray":
    import numpy as np

    out = []
    for h in PALETTE_HEX:
        h = h.lstrip("#")
        out.append([int(h[i : i + 2], 16) for i in (0, 2, 4)])
    return np.array(out, dtype=np.uint8)


NODATA_RGB = tuple(int(NODATA_FACE.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
OUTSIDE_RGB = tuple(int(OUTSIDE_FILL.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
WHITE_RGB = (255, 255, 255)
