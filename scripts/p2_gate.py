"""P2 gate: palette, trials, northern block, checkpoint."""



from __future__ import annotations



import json



import pandas as pd



from rainfall.config import load_config, resolve_path

from rainfall.palette_lab import validate_palette

from rainfall.render_daily import northern_grey_report, run_p2_trials

from rainfall.render_geom import load_render_geometry





def main() -> None:

    cfg = load_config()

    print("=== P2.6 palette ===")

    pal = validate_palette()

    print(json.dumps({k: pal[k] for k in pal if k != "palette_hex"}, indent=2))



    geom = load_render_geometry(cfg)

    dates = [pd.Timestamp("2026-09-19"), pd.Timestamp("2025-05-31")]

    print("\n=== P2.5 northern grey block ===")

    nr = northern_grey_report(geom, dates, resolve_path(cfg["paths"]["processed_enriched"]))

    print(nr.to_string(index=False))

    leh = nr[nr["district"].astype(str).str.contains("Leh|Kargil", case=False, na=False)]

    if len(leh):

        print("Leh/Kargil rows:", leh.to_string(index=False))

    else:

        print("No Leh/Kargil polygon in north sample; grey is likely OUTSIDE_FILL or no_data hatch.")



    print("\n=== P2 trials ===")

    results = run_p2_trials(cfg)

    for r in results:

        print(r)

    payload = {"palette": pal, "trials": results, "northern_report": nr.to_dict(orient="records")}

    resolve_path("outputs/checkpoints/p2_gate.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")





if __name__ == "__main__":

    main()

