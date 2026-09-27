"""Investigate 'Unknown Districts Of India' rows (Part A5)."""

from __future__ import annotations

import pandas as pd

from rainfall.config import resolve_path
from rainfall.io import load_parquet
from rainfall.validate_crosswalk import load_imd_gist


def run_unknown_report() -> None:
    df = load_parquet(sample=False)
    unk = df[df["district"].astype(str).str.contains("Unknown Districts", case=False, na=False)].copy()
    imd = load_imd_gist()
    imd_ids = set(imd["obj_id"].dropna().astype(int))

    by_state = unk.groupby("state", observed=True).agg(
        n_rows=("date", "size"),
        n_days=("date", "nunique"),
        n_null_actual=("daily_actual_mm", lambda s: s.isna().sum()),
        mean_actual=("daily_actual_mm", "mean"),
        obj_ids=("obj_id", lambda s: sorted({int(x) for x in s.dropna().unique()})),
    )

    by_year = unk.groupby(unk["date"].dt.year, observed=True).size()

    # Obj_Id mapping attempt
    relabel = []
    for oid in unk["obj_id"].dropna().unique():
        oid = int(oid)
        rows = unk[unk["obj_id"] == oid]
        if oid in imd_ids:
            imd_row = imd[imd["obj_id"] == oid].iloc[0]
            relabel.append({"obj_id": oid, "imd_name": imd_row["district_name"], "imd_state": imd_row["state_name"], "n_rows": len(rows)})
        else:
            relabel.append({"obj_id": oid, "imd_name": None, "n_rows": len(rows)})

    lines = [
        "# Unknown Districts Of India",
        "",
        f"Total rows: **{len(unk):,}**",
        "",
        "## By state",
        by_state.reset_index().to_markdown(index=False),
        "",
        "## By year (row count)",
        by_year.to_frame("n_rows").to_markdown(),
        "",
        "## Values",
        f"- Rows with NaN daily actual: **{unk['daily_actual_mm'].isna().sum()}**",
        f"- Rows with non-NaN actual: **{unk['daily_actual_mm'].notna().sum()}**",
        "",
        "## Obj_Id notes",
        "Obj_Id 235 and 811 appear under Raigarh (Chhattisgarh) in named districts; Unknown rows share overlapping Obj_Id patterns.",
        "",
        "### Obj_Id → IMD name (where id exists in gist)",
        pd.DataFrame(relabel).to_markdown(index=False),
        "",
        "## Decision",
        "Unknown rows with mappable Obj_Id to a **single** IMD district will be **relabeled** in M3 (`qc_relabelled_unknown`). "
        "Remaining Unknown rows stay excluded with `qc_placeholder_district`.",
        "",
    ]
    out = resolve_path("outputs/reports/unknown_districts.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
