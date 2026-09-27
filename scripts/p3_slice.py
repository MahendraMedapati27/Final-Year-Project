"""P3.4 slice render + resume test."""



from __future__ import annotations



import json



import pandas as pd



from rainfall.config import resolve_path

from rainfall.render_batch import render_dates





def main() -> None:

    d1 = pd.date_range("2025-05-25", "2025-06-23", freq="D")

    d2 = pd.date_range("2026-09-13", "2026-09-19", freq="D")

    dates = [pd.Timestamp(x) for x in d1] + [pd.Timestamp(x) for x in d2]

    s1 = render_dates(dates, workers=1, overwrite=False, rebuild_matrix=True)

    print("first pass", s1)

    s2 = render_dates(dates, workers=1, overwrite=False, rebuild_matrix=False)

    print("second pass (expect all skipped)", s2)

    assert s2["n_rendered"] == 0, "resume failed: re-rendered files"

    all_dates = pd.read_parquet(resolve_path("data/processed/rainfall_enriched.parquet"), columns=["date"])["date"].nunique()

    spf = s1.get("seconds_per_frame_wall") or (s1["seconds_total"] / len(dates))
    extrap = spf * all_dates

    payload = {"slice_first": s1, "slice_resume": s2, "extrapolated_full_seconds": extrap}

    resolve_path("outputs/checkpoints/p3_gate.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("extrapolated full render hours", extrap / 3600)





if __name__ == "__main__":
    import multiprocessing as mp

    mp.freeze_support()
    main()

