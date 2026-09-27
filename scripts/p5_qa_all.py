"""Step 5 QA over all daily map PNGs."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from rainfall.classes import daily_intensity_class
from rainfall.config import load_config, resolve_path
from rainfall.palette_lab import NODATA_FACE, OUTSIDE_FILL, PALETTE_HEX
from rainfall.render_daily import DailyMapRenderer
from rainfall.render_geom_cache import load_geometry_cached


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _expected_rgb(class_id: int) -> tuple[int, int, int]:
    if class_id < 0:
        return _hex_rgb(NODATA_FACE)
    return _hex_rgb(PALETTE_HEX[class_id])


def _pixel_from_canvas(fig, ax, lon: float, lat: float) -> tuple[int, int, int]:
    fig.canvas.draw()
    w, h = fig.canvas.get_width_height()
    buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
    px, py = ax.transData.transform((lon, lat))
    xi = int(max(0, min(w - 1, px)))
    yi = int(max(0, min(h - 1, h - py)))
    return tuple(int(x) for x in buf[yi, xi])


def qa_maps(
    maps_root: Path,
    manifest_path: Path,
    n_data_dates: int,
    *,
    sample: int | None = None,
    rerender_dates: list[str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    cfg = load_config()
    pngs = sorted(maps_root.rglob("rainfall_actual_*.png"))
    checks: list[dict] = []
    t0 = time.perf_counter()

    if sample is None:
        checks.append(
            {
                "check": "png_count",
                "pass": len(pngs) == n_data_dates,
                "got": len(pngs),
                "expected": n_data_dates,
            }
        )
    else:
        checks.append(
            {
                "check": "png_count_sample_mode",
                "pass": len(pngs) >= sample,
                "got": len(pngs),
                "expected": f">= {sample} (full {n_data_dates} deferred)",
            }
        )
    bad_size = [str(p) for p in pngs if p.stat().st_size == 0]
    checks.append({"check": "no_zero_byte", "pass": len(bad_size) == 0, "got": len(bad_size), "expected": 0})
    sizes = {Image.open(p).size for p in pngs}
    checks.append(
        {
            "check": "identical_dimensions",
            "pass": len(sizes) == 1,
            "got": str(sizes) if len(sizes) <= 3 else f"{len(sizes)} distinct",
            "expected": "one size",
        }
    )
    err = resolve_path("logs/render_errors.csv")
    err_body = err.read_text(encoding="utf-8").strip() if err.exists() else ""
    err_ok = err_body == "" or err_body == "date,error"
    checks.append({"check": "render_errors_empty", "pass": err_ok, "got": err_ok, "expected": True})

    man = pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame()
    if sample is None:
        checks.append(
            {
                "check": "manifest_complete",
                "pass": len(man) >= n_data_dates,
                "got": len(man),
                "expected": n_data_dates,
            }
        )

    if not man.empty and "n_districts_with_data" in man.columns:
        legend_ok = True
        bad_legend: list[str] = []
        for _, row in man.iterrows():
            nd = int(row.get("n_districts_with_data") or 0)
            nn = int(row.get("n_no_data") or 0)
            if nd + nn < 750:
                legend_ok = False
                bad_legend.append(str(row["date"]))
        checks.append(
            {
                "check": "legend_counts_vs_districts",
                "pass": legend_ok,
                "got": bad_legend[:5],
                "expected": "n_data+n_no_data plausible",
            }
        )

    npz = np.load(resolve_path("data/processed/render_matrix.npz"), allow_pickle=False)
    dates_np = npz["dates"]
    class_idx = npz["class_idx"]
    shp_ids = npz["shp_ids"].astype(int)
    date_to_t = {str(np.datetime_as_string(d, unit="D")): i for i, d in enumerate(dates_np)}

    geom = load_geometry_cached(cfg)
    gdf = geom.gdf.set_index("shp_id")
    rep_cache: dict[int, tuple[float, float]] = {}
    for sid in shp_ids:
        if sid in gdf.index:
            rep_cache[int(sid)] = gdf.loc[sid].geometry.representative_point().coords[0]

    date_list = [p.stem.replace("rainfall_actual_", "") for p in pngs]
    if sample:
        date_list = date_list[:sample]

    colour_fail: list[str] = []
    white_fail: list[str] = []
    r = DailyMapRenderer(cfg=cfg, geom=geom)
    cols = ["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std", "qc_isolated_extreme"]

    w, h = r.fig.canvas.get_width_height()

    def _rgb_at(lon: float, lat: float, buf: np.ndarray) -> tuple[int, int, int]:
        px, py = r.ax_main.transData.transform((lon, lat))
        xi = int(max(0, min(w - 1, px)))
        yi = int(max(0, min(h - 1, h - py)))
        return tuple(int(x) for x in buf[yi, xi])

    for ds in date_list:
        ti = date_to_t.get(ds)
        if ti is None:
            continue
        day = pd.read_parquet(
            resolve_path(cfg["paths"]["processed_enriched"]),
            filters=[("date", "=", pd.Timestamp(ds))],
            columns=cols,
        )
        r.draw_date(pd.Timestamp(ds), day)
        r.fig.canvas.draw()
        buf = np.asarray(r.fig.canvas.buffer_rgba())[:, :, :3]
        row_classes = class_idx[ti]
        for j, sid in enumerate(shp_ids):
            cid = int(row_classes[j])
            if cid < 0 and sid not in rep_cache:
                continue
            if sid not in rep_cache:
                continue
            lon, lat = rep_cache[int(sid)]
            rgb = _rgb_at(lon, lat, buf)
            exp = _expected_rgb(cid)
            if sum(abs(rgb[k] - exp[k]) for k in range(3)) > 48:
                colour_fail.append(f"{ds}:shp{sid}")
            if rgb == (255, 255, 255) and cid >= 0:
                white_fail.append(f"{ds}:shp{sid}")

    checks.append(
        {
            "check": "colour_vs_render_matrix",
            "pass": len(colour_fail) == 0,
            "got": len(colour_fail),
            "expected": 0,
        }
    )
    checks.append(
        {
            "check": "no_white_in_districts",
            "pass": len(white_fail) == 0,
            "got": len(white_fail),
            "expected": 0,
        }
    )

    elapsed = time.perf_counter() - t0
    meta = {
        "colour_mismatch_sample": colour_fail[:20],
        "white_inside_sample": white_fail[:20],
        "qa_seconds": elapsed,
    }
    return pd.DataFrame(checks), meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=None)
    args = ap.parse_args()
    print("p5_qa_all: loading date count…", flush=True)
    en = pd.read_parquet(resolve_path("data/processed/rainfall_enriched.parquet"), columns=["date"])
    n = int(en["date"].nunique())
    root = resolve_path("outputs/maps/daily_actual")
    man = root / "manifest.csv"
    print(f"p5_qa_all: qa_maps sample={args.sample} expected_dates={n}", flush=True)
    df, meta = qa_maps(root, man, n, sample=args.sample)
    print(df.to_string(index=False))
    print("meta", meta, flush=True)
    payload = {"checks": df.to_dict(orient="records"), "meta": meta, "all_pass": bool(df["pass"].all())}
    resolve_path("outputs/checkpoints/p5_qa.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.sample is None and not df["pass"].all():
        sys.exit(1)


if __name__ == "__main__":
    main()
