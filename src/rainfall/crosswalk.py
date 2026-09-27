"""Dataset ↔ polygon crosswalk (PROMPT §7.3)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from rainfall.config import load_config, resolve_path
from rainfall.io import load_parquet
from rainfall.names import district_key, load_alias_maps, normalize_district, normalize_state

logger = logging.getLogger(__name__)

LATEST_DATE = pd.Timestamp("2026-09-19")


@dataclass
class MatchStats:
    exact: int = 0
    normalized: int = 0
    fuzzy: int = 0
    manual: int = 0
    unmatched: int = 0
    total: int = 0

    def rates(self) -> dict[str, float]:
        t = max(self.total, 1)
        matched = self.exact + self.normalized + self.fuzzy + self.manual
        return {
            "exact_pct": 100 * self.exact / t,
            "normalized_pct": 100 * (self.exact + self.normalized) / t,
            "fuzzy92_pct": 100 * (self.exact + self.normalized + self.fuzzy) / t,
            "matched_pct": 100 * matched / t,
            "unmatched_pct": 100 * self.unmatched / t,
        }


def load_manual_overrides() -> dict[tuple[str, str], int]:
    cfg = load_config()
    path = resolve_path(cfg["paths"]["manual_overrides"])
    out: dict[tuple[str, str], int] = {}
    if not path.exists():
        return out
    df = pd.read_csv(path, comment="#")
    for _, row in df.iterrows():
        if pd.isna(row.get("dataset_state")) or str(row.get("dataset_state", "")).strip() == "":
            continue
        st = str(row["dataset_state"]).strip()
        dist = str(row["dataset_district"]).strip()
        out[(st, dist)] = int(row["shp_id"])
    return out


def dataset_target_latest(df: pd.DataFrame) -> pd.DataFrame:
    sub = df[df["date"] == LATEST_DATE][["state", "district"]].drop_duplicates()
    sub = sub[~sub["district"].astype(str).str.contains("Unknown Districts", case=False, na=False)]
    sub["weight"] = 1
    return sub.reset_index(drop=True)


def dataset_target_weighted(master_path: Path | None = None) -> pd.DataFrame:
    master_path = master_path or resolve_path("outputs/tables/district_master_full.csv")
    master = pd.read_csv(master_path)
    master = master[~master["district"].astype(str).str.contains("Unknown Districts", case=False, na=False)]
    master["weight"] = master["n_days"]
    return master[["state", "district", "weight", "first_date", "last_date"]].copy()


def _fuzzy_best(
    query_dist: str,
    poly_dist_keys: list[str],
    poly_ids: list[int],
    min_score: float,
) -> tuple[int | None, float, bool]:
    scores = [(fuzz.WRatio(query_dist, pk), pid, pk) for pk, pid in zip(poly_dist_keys, poly_ids)]
    scores.sort(reverse=True, key=lambda x: x[0])
    if not scores or scores[0][0] < min_score:
        return None, 0.0, False
    top = scores[0][0]
    second = scores[1][0] if len(scores) > 1 else 0.0
    margin = top - second
    return scores[0][1], float(top), margin >= 5


def match_dataset_to_polygons(
    polygons: gpd.GeoDataFrame,
    targets: pd.DataFrame,
    cfg: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, MatchStats]:
    """One-to-one matching per state; returns crosswalk rows for all target districts."""
    cfg = cfg or load_config()
    cw = cfg["crosswalk"]
    auto = float(cw["fuzzy_auto_accept"])
    review_min = float(cw["fuzzy_review_min"])
    min_assign = float(cw["fuzzy_min_assign"])

    manual = load_manual_overrides()
    poly = polygons.copy()
    poly["state_std"] = poly["state_std"].astype(str)
    poly["district_std"] = poly["district_std"].astype(str)
    poly["shp_id"] = poly["shp_id"].astype(int)

    assigned_poly: set[int] = set()
    rows: list[dict[str, Any]] = []
    stats = MatchStats(total=len(targets))

    for state in targets["state"].unique():
        t_sub = targets[targets["state"] == state].copy()
        p_sub = poly[poly["state_std"] == normalize_state(state)]
        if p_sub.empty:
            p_sub = poly[poly["state_name"].astype(str).str.upper() == str(state).upper()]

        poly_by_key = {
            (r.state_std, r.district_std): int(r.shp_id)
            for r in p_sub.itertuples()
        }
        poly_dist_keys = [r.district_std for r in p_sub.itertuples()]
        poly_ids = [int(r.shp_id) for r in p_sub.itertuples()]

        matched_idx: set[int] = set()

        # Pass 0: manual
        for i, row in t_sub.iterrows():
            mk = (str(row["state"]), str(row["district"]))
            if mk in manual:
                sid = manual[mk]
                if sid in assigned_poly:
                    continue
                assigned_poly.add(sid)
                matched_idx.add(i)
                stats.manual += 1
                rows.append(
                    {
                        "dataset_state": row["state"],
                        "dataset_district": row["district"],
                        "state_std": normalize_state(row["state"]),
                        "district_std": normalize_district(row["district"], row["state"]),
                        "shp_id": sid,
                        "match_method": "manual",
                        "match_score": 100.0,
                        "needs_review": False,
                        "note": "manual_overrides.csv",
                    }
                )

        # Pass 1: exact raw
        for i, row in t_sub.iterrows():
            if i in matched_idx:
                continue
            sk, dk = district_key(row["state"], row["district"])
            pid = poly_by_key.get((sk, dk))
            if pid is not None and pid not in assigned_poly:
                assigned_poly.add(pid)
                matched_idx.add(i)
                stats.exact += 1
                rows.append(_row(row, pid, "exact", 100.0, False, ""))

        # Pass 2: normalized keys already in exact — alias pass for dataset side only
        for i, row in t_sub.iterrows():
            if i in matched_idx:
                continue
            sk, dk = district_key(row["state"], row["district"])
            for (psk, pdk), pid in poly_by_key.items():
                if psk == sk and pdk == dk and pid not in assigned_poly:
                    assigned_poly.add(pid)
                    matched_idx.add(i)
                    stats.normalized += 1
                    rows.append(_row(row, pid, "alias_normalized", 99.0, False, ""))
                    break

        # Pass 3: fuzzy within state
        review: list[tuple[int, pd.Series, int, float]] = []
        for i, row in t_sub.iterrows():
            if i in matched_idx:
                continue
            sk, dk = district_key(row["state"], row["district"])
            avail_keys = [k for k, pid in poly_by_key.items() if pid not in assigned_poly and k[0] == sk]
            if not avail_keys:
                continue
            keys = [k[1] for k in avail_keys]
            ids = [poly_by_key[k] for k in avail_keys]
            pid, score, ok_margin = _fuzzy_best(dk, keys, ids, review_min)
            if pid is None:
                continue
            needs = score < auto or not ok_margin
            if score >= auto and ok_margin:
                assigned_poly.add(pid)
                matched_idx.add(i)
                stats.fuzzy += 1
                rows.append(_row(row, pid, "fuzzy", score, needs, ""))
            else:
                review.append((i, row, pid, score))

        # Pass 4: Hungarian on remaining
        rem_targets = [(i, row) for i, row in t_sub.iterrows() if i not in matched_idx]
        rem_polys = p_sub[~p_sub["shp_id"].isin(assigned_poly)]
        if rem_targets and len(rem_polys):
            n_t, n_p = len(rem_targets), len(rem_polys)
            cost = np.zeros((n_t, n_p))
            for ti, (_, trow) in enumerate(rem_targets):
                _, dk = district_key(trow["state"], trow["district"])
                for pj, prow in enumerate(rem_polys.itertuples()):
                    cost[ti, pj] = 100 - fuzz.WRatio(dk, prow.district_std)
            ri, ci = linear_sum_assignment(cost)
            for ti, pj in zip(ri, ci):
                score = 100 - cost[ti, pj]
                if score < min_assign:
                    continue
                i, trow = rem_targets[ti]
                pid = int(rem_polys.iloc[pj]["shp_id"])
                if pid in assigned_poly or i in matched_idx:
                    continue
                assigned_poly.add(pid)
                matched_idx.add(i)
                stats.fuzzy += 1
                needs = score < auto
                rows.append(_row(trow, pid, "hungarian", score, needs, ""))

        # Unmatched
        for i, row in t_sub.iterrows():
            if i in matched_idx:
                continue
            stats.unmatched += 1
            note = "no polygon in layer"
            if "Unknown Districts" in str(row["district"]):
                note = "placeholder district — exclude from maps"
            rows.append(_row(row, np.nan, "unmatched", 0.0, True, note))

    crosswalk = pd.DataFrame(rows)
    return crosswalk, stats


def _row(row: pd.Series, pid: int, method: str, score: float, review: bool, note: str) -> dict[str, Any]:
    return {
        "dataset_state": row["state"],
        "dataset_district": row["district"],
        "state_std": normalize_state(row["state"]),
        "district_std": normalize_district(row["district"], row["state"]),
        "shp_id": pid,
        "match_method": method,
        "match_score": score,
        "needs_review": review,
        "note": note,
    }


def score_polygons_against_targets(
    polygons: gpd.GeoDataFrame,
    targets: pd.DataFrame,
    weighted: bool = False,
) -> MatchStats:
    cw, stats = match_dataset_to_polygons(polygons, targets)
    if weighted and "weight" in targets.columns:
        w = targets.set_index(["state", "district"])["weight"]
        cw["_w"] = cw.apply(lambda r: w.get((r["dataset_state"], r["dataset_district"]), 1), axis=1)
        matched_w = cw[cw["match_method"] != "unmatched"]["_w"].sum()
        total_w = cw["_w"].sum()
        stats.rates = lambda: {"weighted_matched_pct": 100 * matched_w / max(total_w, 1)}  # type: ignore
    return stats


def _flag_historical_and_placeholders(cw: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    master = master.set_index(["state", "district"])
    cw = cw.copy()
    for i, row in cw.iterrows():
        dist = str(row["dataset_district"])
        if "Unknown Districts Of India" in dist:
            cw.at[i, "note"] = "placeholder — exclude from maps (qc_placeholder_district)"
            cw.at[i, "needs_review"] = True
            continue
        key = (row["dataset_state"], row["dataset_district"])
        if key not in master.index:
            continue
        m = master.loc[key]
        if pd.isna(row["shp_id"]):
            cw.at[i, "note"] = (
                f"no polygon; active {m['first_date']}–{m['last_date']} "
                f"({m['n_days']} days) — name not in boundary layer"
            )
    return cw


def build_crosswalk_from_gpkg(gpkg_path: Path | None = None) -> Path:
    cfg = load_config()
    gpkg_path = gpkg_path or resolve_path(cfg["paths"]["geo_districts"])
    polygons = gpd.read_file(gpkg_path, layer="districts")
    df = load_parquet(sample=False)
    master_full = pd.read_csv(resolve_path("outputs/tables/district_master_full.csv"))
    targets_latest = dataset_target_latest(df)
    targets_all = dataset_target_weighted()

    cw_latest, stats_latest = match_dataset_to_polygons(polygons, targets_latest)
    cw_all, _ = match_dataset_to_polygons(polygons, targets_all)

    out_tables = resolve_path(cfg["outputs"]["tables"])
    out_proc = resolve_path(cfg["paths"]["crosswalk"])
    out_proc.parent.mkdir(parents=True, exist_ok=True)
    out_tables.mkdir(parents=True, exist_ok=True)

    cw_all = _flag_historical_and_placeholders(cw_all, master_full)
    cw_all.to_csv(out_proc, index=False)
    cw_latest.to_csv(out_tables / "crosswalk_latest_date.csv", index=False)

    unmatched_d = cw_all[cw_all["match_method"] == "unmatched"]
    unmatched_p = polygons[~polygons["shp_id"].isin(cw_all["shp_id"].dropna().astype(int))]
    needs = cw_all[cw_all["needs_review"] | (cw_all["match_method"] == "unmatched")]

    unmatched_d.to_csv(out_tables / "crosswalk_unmatched_dataset.csv", index=False)
    unmatched_p[["shp_id", "state_std", "district_std", "state_name", "district_name"]].to_csv(
        out_tables / "crosswalk_unmatched_polygons.csv", index=False
    )
    needs.to_csv(out_tables / "crosswalk_needs_review.csv", index=False)

    rate = stats_latest.rates()["matched_pct"]
    logger.info("Latest-date match rate: %.2f%%", rate)
    print(f"Crosswalk: {out_proc}")
    print(f"Latest-date matched: {rate:.2f}%")
    return out_proc


def append_resolved_aliases(crosswalk: pd.DataFrame) -> None:
    """Append successful fuzzy/normalized matches to name_aliases.csv."""
    cfg = load_config()
    path = resolve_path(cfg["paths"]["name_aliases"])
    existing = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["type", "dataset_value", "canonical_value", "note"])
    new_rows = []
    for _, r in crosswalk.iterrows():
        if r["match_method"] in ("fuzzy", "hungarian", "alias_normalized") and pd.notna(r["shp_id"]):
            if str(r["dataset_district"]) != str(r["district_std"]):
                new_rows.append(
                    {
                        "type": "district",
                        "dataset_value": r["dataset_district"],
                        "canonical_value": r["district_std"],
                        "note": f"crosswalk {r['match_method']}",
                    }
                )
    if new_rows:
        pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True).drop_duplicates(
            subset=["type", "dataset_value"]
        ).to_csv(path, index=False)
        load_alias_maps.cache_clear()
