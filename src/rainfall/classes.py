"""IMD intensity and departure category helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd

INTENSITY_BOUNDS = [0.0, 0.1, 2.5, 15.6, 64.5, 115.6, 204.5, np.inf]
INTENSITY_LABELS = [
    "No Rain",
    "Very Light",
    "Light",
    "Moderate",
    "Heavy",
    "Very Heavy",
    "Extremely Heavy",
]


def daily_intensity_class(mm: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Return (ordered categorical label, int code 0-6)."""
    x = mm.astype(float)
    codes = pd.Series(np.nan, index=mm.index, dtype="float")
    for i, (lo, hi) in enumerate(zip(INTENSITY_BOUNDS[:-1], INTENSITY_BOUNDS[1:])):
        if i == 0:
            mask = (x.isna()) | (x < 0.1)
        elif i == 1:
            mask = (x >= 0.1) & (x < 2.5)
        else:
            mask = (x >= lo) & (x < hi)
        codes[mask] = i
    codes[x >= 204.5] = 6
    labels = codes.map(dict(enumerate(INTENSITY_LABELS)))
    return labels.astype("category"), codes.astype("Int8")


def departure_category(pct: pd.Series) -> pd.Series:
    out = pd.Series(index=pct.index, dtype="object")
    for v in pct.index:
        p = pct.loc[v]
        if pd.isna(p):
            out.loc[v] = np.nan
            continue
        if p >= 60:
            out.loc[v] = "LE"
        elif p >= 20:
            out.loc[v] = "E"
        elif p >= -19:
            out.loc[v] = "N"
        elif p >= -59:
            out.loc[v] = "D"
        elif p >= -99:
            out.loc[v] = "LD"
        elif p == -100:
            out.loc[v] = "NR"
        else:
            out.loc[v] = "ND"
    return out


def guarded_departure(actual: pd.Series, normal: pd.Series, guard: float) -> pd.Series:
    dep = (actual - normal) / normal * 100.0
    return dep.where(normal >= guard)
