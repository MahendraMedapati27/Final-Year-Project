"""P1b follow-up analyses and checkpoints."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from rainfall.config import resolve_path


def dedupe_reconciliation() -> pd.DataFrame:
    dup = pd.read_csv(resolve_path("outputs/tables/duplicates_resolved.csv"))
    n_groups = len(dup)
    by_rule = dup["rule"].value_counts().sort_index()
    by_n = dup.groupby("n_in_group", observed=True).size().reset_index(name="n_groups")
    n_ge3 = int((dup["n_in_group"] >= 3).sum())
    tbl = pd.DataFrame({"rule": by_rule.index, "n_groups": by_rule.values})
    tbl.loc[len(tbl)] = {"rule": "_TOTAL_", "n_groups": int(by_rule.sum())}
    tbl.to_csv(resolve_path("outputs/tables/dedupe_reconciliation.csv"), index=False)
    by_n.to_csv(resolve_path("outputs/tables/dedupe_groups_by_size.csv"), index=False)
    out = {
        "n_groups_logged": n_groups,
        "sum_by_rule": int(by_rule.sum()),
        "groups_with_3plus_rows": n_ge3,
        "rules": by_rule.to_dict(),
    }
    Path(resolve_path("outputs/checkpoints/p1b_dedupe.json")).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return tbl


def unresolvable_analysis() -> dict:
    dup = pd.read_csv(resolve_path("outputs/tables/duplicates_resolved.csv"))
    un = dup[dup["rule"] == "conflict_unresolvable"].copy()
    un["year"] = pd.to_datetime(un["date"]).dt.year
    by_state = un.groupby("state", observed=True).size().sort_values(ascending=False)
    by_dist = un.groupby(["state", "district"], observed=True).size().sort_values(ascending=False).head(20)
    by_year = un.groupby("year", observed=True).size()

    en = pd.read_parquet(
        resolve_path("data/processed/rainfall_enriched.parquet"),
        columns=["state", "district", "date", "daily_actual_mm", "qc_dup_unresolvable"],
    )
    un_rows = en[en["qc_dup_unresolvable"] == True]  # noqa: E712
    runs = []
    for (st, dist), g in un_rows.groupby(["state", "district"], observed=True):
        g = g.sort_values("date")
        d = g["date"].diff().dt.days.fillna(1)
        run = 1
        max_run = 1
        for gap in d.iloc[1:]:
            if gap == 1:
                run += 1
                max_run = max(max_run, run)
            else:
                run = 1
        runs.append({"state": st, "district": dist, "n_nan_days": len(g), "longest_run": max_run})
    runs_df = pd.DataFrame(runs).sort_values("longest_run", ascending=False).head(10)

    examples = un.dropna(subset=["val_a", "val_b"]).head(5)
    un.to_csv(resolve_path("outputs/tables/unresolvable_dup_groups.csv"), index=False)
    by_state.to_csv(resolve_path("outputs/tables/unresolvable_by_state.csv"), header=["n"])
    payload = {
        "n_unresolvable": len(un),
        "by_state_top5": by_state.head().to_dict(),
        "by_year": by_year.to_dict(),
        "top10_longest_nan_runs": runs_df.to_dict(orient="records"),
        "examples": examples[["state", "district", "date", "val_a", "val_b", "ref_r", "chosen"]].to_dict(orient="records"),
    }
    Path(resolve_path("outputs/checkpoints/p1b_unresolvable.json")).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload
