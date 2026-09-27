"""P2 layout pixel tests and palette gate."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from rainfall.config import load_config, resolve_path
from rainfall.palette_lab import NODATA_FACE, OUTSIDE_FILL, PALETTE_HEX, validate_palette
from rainfall.render_daily import DailyMapRenderer, render_one_date
from rainfall.render_geom import load_render_geometry
from rainfall.render_layout import explain_old_test_false_negative, ui_overlaps_land


def _allowed_rgb() -> set[tuple[int, int, int]]:
    allowed = set()
    for h in PALETTE_HEX + [NODATA_FACE, OUTSIDE_FILL, "#FFFFFF", "#444444", "#404040", "#101010", "#666666", "#333333"]:
        h = h.lstrip("#")
        allowed.add(tuple(int(h[i : i + 2], 16) for i in (0, 2, 4)))
    return allowed


def _pixel_from_canvas(fig, ax, lon: float, lat: float) -> tuple[int, int, int]:
    fig.canvas.draw()
    w, h = fig.canvas.get_width_height()
    buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
    px, py = ax.transData.transform((lon, lat))
    xi = int(max(0, min(w - 1, px)))
    yi = int(max(0, min(h - 1, h - py)))
    return tuple(int(x) for x in buf[yi, xi])


@pytest.mark.full
def test_palette_ciede2000_gate():
    assert validate_palette()["pass_all"]


@pytest.mark.full
def test_ui_pixel_overlap_not_on_land():
    """Legend/stats/titles/footer must not cover land pixels (map-only mask)."""
    print(explain_old_test_false_negative())
    cfg = load_config()
    geom = load_render_geometry(cfg)
    r = DailyMapRenderer(cfg=cfg, geom=geom)
    for d in (pd.Timestamp("2026-09-19"), pd.Timestamp("2021-01-31")):
        cols = ["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std", "qc_isolated_extreme"]
        day = pd.read_parquet(resolve_path(cfg["paths"]["processed_enriched"]), filters=[("date", "=", d)], columns=cols)
        r.draw_date(d, day)
        overlaps = ui_overlaps_land(r, include_legend=False)
        bad = [k for k, v in overlaps.items() if v]
        assert not bad, f"{d.date()} UI overlaps land: {bad}"


@pytest.mark.full
def test_no_white_inside_every_polygon_rep_point():
    cfg = load_config()
    out_dir = resolve_path("outputs/maps/p2_trial")
    dates = [pd.Timestamp("2026-09-19"), pd.Timestamp("2021-01-31")]
    allowed = _allowed_rgb()
    geom = load_render_geometry(cfg)
    r = DailyMapRenderer(cfg=cfg, geom=geom)
    cols = ["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std", "qc_isolated_extreme"]
    for d in dates:
        p = out_dir / f"rainfall_actual_{d.date()}.png"
        if not p.exists():
            render_one_date(d, p, cfg)
        day = pd.read_parquet(resolve_path(cfg["paths"]["processed_enriched"]), filters=[("date", "=", d)], columns=cols)
        r.draw_date(d, day)
        skip = set(int(x) for x in list(geom.an_shp_ids) + list(geom.ld_shp_ids))
        mainland = geom.gdf[~geom.gdf["shp_id"].isin(skip)]
        rj = mainland[mainland["state_name"].astype(str).str.contains("Rajasthan|Gujarat", case=False, na=False)]
        sample = pd.concat([rj, mainland.sample(min(100, len(mainland)), random_state=1)]).drop_duplicates("shp_id")
        for _, row in sample.iterrows():
            cx, cy = row.geometry.representative_point().coords[0]
            rgb = _pixel_from_canvas(r.fig, r.ax_main, cx, cy)
            if rgb == (255, 255, 255):
                pytest.fail(f"{d.date()} white at district {row['district_name']} shp_id={int(row['shp_id'])}")
            assert min(sum(abs(rgb[i] - a[i]) for i in range(3)) for a in allowed) < 60


@pytest.mark.full
def test_trial_pngs_same_dimensions():
    d1 = resolve_path("outputs/maps/p2_trial/rainfall_actual_2026-09-19.png")
    d2 = resolve_path("outputs/maps/p2_trial/rainfall_actual_2021-01-31.png")
    if not d1.exists() or not d2.exists():
        pytest.skip("trial PNGs not built yet")
    assert Image.open(d1).size == Image.open(d2).size
