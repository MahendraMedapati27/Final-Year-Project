"""Duplicate-key analysis report (M2 step 0b)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from rainfall.config import project_root, resolve_path
from rainfall.io import load_parquet

VALUE_COLS = [
    "daily_actual_mm",
    "daily_normal_mm",
    "daily_departure_pct_provided",
    "obj_id",
]


def _rows_equal(a: pd.Series, b: pd.Series, cols: list[str]) -> bool:
    for c in cols:
        va, vb = a.get(c), b.get(c)
        if pd.isna(va) and pd.isna(vb):
            continue
        if pd.isna(va) or pd.isna(vb):
            return False
        if c == "obj_id":
            if int(va) != int(vb):
                return False
        elif isinstance(va, (float, np.floating)) and isinstance(vb, (float, np.floating)):
            if not np.isclose(float(va), float(vb), rtol=0, atol=1e-4):
                return False
        elif str(va) != str(vb):
            return False
    return True


def run_duplicates_analysis() -> Path:
    df = load_parquet(sample=False)
    key = ["state", "district", "date"]
    dup_mask = df.duplicated(subset=key, keep=False)
    dups = df.loc[dup_mask].copy()
    dups["year"] = pd.to_datetime(dups["date"]).dt.year

    groups = dups.groupby(key, observed=True)
    n_groups = groups.ngroups

    by_year = dups.groupby("year", observed=True).apply(
        lambda g: pd.Series({"n_dup_rows": len(g), "n_groups": g.groupby(key, observed=True).ngroups}),
        include_groups=False,
    )
    by_state = (
        dups.groupby("state", observed=True)
        .size()
        .sort_values(ascending=False)
        .head(15)
        .reset_index(name="dup_rows")
    )

    obj_null = dups["obj_id"].isna()
    split_obj = pd.Series(
        {
            "both_obj_null": int((dups.groupby(key, observed=True)["obj_id"].apply(lambda s: s.isna().all())).sum()),
            "mixed_obj_null": int((dups.groupby(key, observed=True)["obj_id"].apply(lambda s: s.isna().any() and s.notna().any())).sum()),
            "neither_obj_null": int((dups.groupby(key, observed=True)["obj_id"].apply(lambda s: s.notna().all())).sum()),
        }
    )

    pattern_counts = {"identical_values": 0, "diff_values": 0, "one_all_nan_actual": 0, "diff_obj_id": 0}
    for _, g in groups:
        if len(g) != 2:
            continue
        r1, r2 = g.iloc[0], g.iloc[1]
        if _rows_equal(r1, r2, VALUE_COLS + ["daily_category_provided"]):
            pattern_counts["identical_values"] += 1
        else:
            pattern_counts["diff_values"] += 1
        if r1["daily_actual_mm"] is pd.NA or (pd.isna(r1["daily_actual_mm"]) and pd.isna(r2["daily_actual_mm"])):
            pattern_counts["one_all_nan_actual"] += 1
        elif pd.isna(r1["daily_actual_mm"]) or pd.isna(r2["daily_actual_mm"]):
            pattern_counts["one_all_nan_actual"] += 1
        if pd.notna(r1["obj_id"]) and pd.notna(r2["obj_id"]) and int(r1["obj_id"]) != int(r2["obj_id"]):
            pattern_counts["diff_obj_id"] += 1

    dup_days = (
        dups.groupby(["state", "district"], observed=True)
        .size()
        .div(2)
        .astype(int)
        .reset_index(name="n_duplicate_days")
        .sort_values("n_duplicate_days", ascending=False)
        .head(30)
    )
    obj_pairs = []
    for (st, dist, _), g in groups:
        ids = sorted({int(x) for x in g["obj_id"].dropna().unique()})
        if len(ids) >= 2:
            obj_pairs.append({"state": st, "district": dist, "obj_ids": " vs ".join(map(str, ids[:3]))})
    pairs_df = pd.DataFrame(obj_pairs)
    top_pairs = pairs_df.groupby(["state", "district"], as_index=False).first().head(30)

    # Obj_Id timeline per (state, district, obj_id)
    tl = (
        df.dropna(subset=["obj_id"])
        .groupby(["state", "district", "obj_id"], observed=True)["date"]
        .agg(first_date="min", last_date="max", n_days="nunique")
        .reset_index()
    )
    pair_rel = []
    seen = set()
    for row in top_pairs.itertuples():
        st, dist = row.state, row.district
        sub = tl[(tl["state"] == st) & (tl["district"] == dist)]
        if len(sub) < 2:
            continue
        sub = sub.sort_values("first_date")
        ids = sub["obj_id"].tolist()
        keyp = (st, dist, tuple(ids))
        if keyp in seen:
            continue
        seen.add(keyp)
        rel = "parallel"
        for i in range(len(sub) - 1):
            a, b = sub.iloc[i], sub.iloc[i + 1]
            if pd.Timestamp(a["last_date"]) < pd.Timestamp(b["first_date"]):
                rel = f"sequential ({int(a['obj_id'])} ends {a['last_date'].date()} before {int(b['obj_id'])} starts {b['first_date'].date()})"
                break
        pair_rel.append(
            {
                "state": st,
                "district": dist,
                "obj_ids": ", ".join(str(int(x)) for x in ids),
                "relationship": rel,
            }
        )
    pair_rel_df = pd.DataFrame(pair_rel).head(20)

    dedupe_rule = (
        "**Proposed M3 rule:** For each `(state, district, date)` group, keep one row: "
        "(1) drop rows with NaN `daily_actual_mm` if another row has a value; "
        "(2) among ties, prefer the row with non-null `obj_id`; "
        "(3) among ties, prefer the `obj_id` whose `(state, district, obj_id)` span covers the row's date "
        "and has the latest `last_date` in the full series (current ID); "
        "(4) if still tied, prefer larger `daily_actual_mm` (conservative for flood reporting). "
        "Log all resolutions to `outputs/tables/duplicates_resolved.csv`."
    )

    out = resolve_path("outputs/reports/duplicates_analysis.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Duplicate key analysis `(state, district, date)`",
        "",
        f"- Duplicate **groups**: {n_groups:,} · duplicate **rows**: {len(dups):,}",
        "",
        "## By calendar year (duplicate rows / groups)",
        by_year.to_markdown(),
        "",
        "## Top states by duplicate row count",
        by_state.to_markdown(index=False),
        "",
        "## Obj_Id null pattern (within duplicate groups)",
        split_obj.to_frame("count").to_markdown(),
        "",
        "## Pairwise pattern (groups with exactly 2 rows)",
        pd.Series(pattern_counts).to_frame("groups").to_markdown(),
        "",
        "## Top 30 districts by duplicate days",
        dup_days.to_markdown(index=False),
        "",
        "## Obj_Id pairs (sample)",
        top_pairs.to_markdown(index=False),
        "",
        "## Obj_Id timeline (replacement vs parallel)",
        pair_rel_df.to_markdown(index=False) if len(pair_rel_df) else "_See district-level pairs above._",
        "",
        "## Proposed dedupe rule (implement in M3)",
        dedupe_rule,
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")
    return out
