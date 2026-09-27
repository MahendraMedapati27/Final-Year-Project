"""Find shp_ids whose rep points sample white on map (before/after path fix)."""

from __future__ import annotations

import pandas as pd
from PIL import Image

from rainfall.config import load_config, resolve_path
from rainfall.render_daily import DailyMapRenderer


def main() -> None:
    cfg = load_config()
    d = pd.Timestamp("2021-01-31")
    cols = ["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std"]
    day = pd.read_parquet(resolve_path(cfg["paths"]["processed_enriched"]), filters=[("date", "=", d)], columns=cols)
    r = DailyMapRenderer(cfg=cfg)
    r.draw_date(d, day)
    p = resolve_path("outputs/maps/p2_trial/rainfall_actual_2021-01-31.png")
    p.parent.mkdir(parents=True, exist_ok=True)
    r.save(p)
    im = __import__("numpy").array(Image.open(p).convert("RGB"))
    rows = []
    g = r.geom.gdf
    skip = set(int(x) for x in list(r.geom.an_shp_ids) + list(r.geom.ld_shp_ids))
    for _, row in g.iterrows():
        sid = int(row["shp_id"])
        if sid in skip:
            continue
        cx, cy = row.geometry.representative_point().coords[0]
        r.fig.canvas.draw()
        px, py = r.ax_main.transData.transform((cx, cy))
        xi, yi = int(px), int(im.shape[0] - py)
        if xi < 0 or yi < 0 or xi >= im.shape[1] or yi >= im.shape[0]:
            continue
        rgb = tuple(int(x) for x in im[yi, xi])
        if rgb == (255, 255, 255) or sum(rgb) > 740:
            rows.append(
                {
                    "shp_id": sid,
                    "state": row["state_name"],
                    "district": row["district_name"],
                    "rgb": rgb,
                    "reason": "interior ring not drawn (exterior-only paths) or geometry gap",
                }
            )
    df = pd.DataFrame(rows)
    out = resolve_path("outputs/tables/white_patch_shp_ids.csv")
    df.to_csv(out, index=False)
    print(f"white/suspect polygons: {len(df)}")
    print(df.head(20).to_string(index=False))
    print("saved", out)


if __name__ == "__main__":
    main()
