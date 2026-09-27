"""State and district name normalization for crosswalk."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
from unidecode import unidecode

from rainfall.config import load_config, resolve_path

BRACKET_RE = re.compile(r"\([^)]*\)")
PUNCT_RE = re.compile(r"[^\w\s]")
SPACE_RE = re.compile(r"\s+")


STATE_CANONICAL: dict[str, str] = {
    "THE DADRA AND NAGAR HAVELI AND DAMAN AND DIU": "DADRA AND NAGAR HAVELI AND DAMAN AND DIU",
    "DADRA & NAGAR HAVELI & DAMAN & DIU": "DADRA AND NAGAR HAVELI AND DAMAN AND DIU",
    "JAMMU AND KASHMIR": "JAMMU AND KASHMIR",
    "JAMMU & KASHMIR": "JAMMU AND KASHMIR",
    "ANDAMAN AND NICOBAR ISLANDS": "ANDAMAN AND NICOBAR",
    "ANDAMAN & NICOBAR ISLANDS": "ANDAMAN AND NICOBAR",
    "ANDAMAN & NICOBAR": "ANDAMAN AND NICOBAR",
    "DADRA,NAGAR HAVELI,DAMAN & DIU": "DADRA AND NAGAR HAVELI AND DAMAN AND DIU",
    "DADRA NAGAR HAVELI DAMAN AND DIU": "DADRA AND NAGAR HAVELI AND DAMAN AND DIU",
}


@lru_cache(maxsize=1)
def load_alias_maps() -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    """Return (district aliases by type+value, state aliases)."""
    cfg = load_config()
    path = resolve_path(cfg["paths"]["name_aliases"])
    dist: dict[tuple[str, str], str] = {}
    state: dict[str, str] = {}
    if path.exists():
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            t = str(row.get("type", "")).strip().lower()
            src = str(row.get("dataset_value", "")).strip()
            dst = str(row.get("canonical_value", "")).strip()
            if not src or not dst:
                continue
            if t == "state":
                state[normalize_key(src, is_state=True)] = normalize_key(dst, is_state=True)
            else:
                dist[(t, normalize_key(src))] = normalize_key(dst)
    return dist, state


def normalize_key(name: str, is_state: bool = False) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = unidecode(str(name)).upper().strip()
    s = s.replace("&", " AND ")
    if is_state:
        s = s.replace(",", " AND ")
    if not is_state:
        s = BRACKET_RE.sub("", s)
        for word in (" DISTRICT", " URBAN", " RURAL"):
            if s.endswith(word):
                s = s[: -len(word)].strip()
    s = PUNCT_RE.sub(" ", s)
    s = SPACE_RE.sub(" ", s).strip()
    if is_state and s in STATE_CANONICAL:
        s = STATE_CANONICAL[s]
    return s


def normalize_state(name: str) -> str:
    _, state_aliases = load_alias_maps()
    key = normalize_key(name, is_state=True)
    return state_aliases.get(key, key)


def normalize_district(name: str, state: str | None = None) -> str:
    dist_aliases, _ = load_alias_maps()
    key = normalize_key(name)
    if ("district", key) in dist_aliases:
        return dist_aliases[("district", key)]
    if state:
        sk = normalize_state(state)
        if ("district", f"{sk}|{key}") in dist_aliases:
            return dist_aliases[("district", f"{sk}|{key}")]
    return key


def district_key(state: str, district: str) -> tuple[str, str]:
    return normalize_state(state), normalize_district(district, state)
