"""Pixel-based UI vs map overlap checks (replaces centroid bbox test)."""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image, ImageDraw

from rainfall.render_daily import DailyMapRenderer


def explain_old_test_false_negative() -> str:
    return (
        "P2.1 used each district representative point in data coordinates transformed to figure "
        "fraction and tested only whether that single point fell inside the legend or stats bbox. "
        "The stats box at the top-right sat over Jammu & Kashmir while rep points (often in the "
        "south of those polygons) stayed outside the box, so the test passed despite overlap."
    )


def _land_mask_lowres(r: DailyMapRenderer, max_px: int = 400) -> tuple[np.ndarray, float]:
    """Rasterize mainland + inset axes to a low-res land mask; returns mask, scale to full fig pixels."""
    fig = r.fig
    fig.canvas.draw()
    fw, fh = fig.get_size_inches()
    full_w, full_h = int(fw * r.dpi), int(fh * r.dpi)
    scale = min(max_px / full_w, max_px / full_h, 1.0)
    tw, th = max(1, int(full_w * scale)), max(1, int(full_h * scale))
    mask = Image.new("L", (tw, th), 0)
    draw = ImageDraw.Draw(mask)
    for ax in (r.ax_main,):
        for path in ax.collections:
            for p in path.get_paths():
                verts = p.vertices
                if len(verts) < 3:
                    continue
                disp = ax.transData.transform(verts)
                fig_xy = fig.transFigure.inverted().transform(disp)
                px = fig_xy[:, 0] * tw
                py = (1.0 - fig_xy[:, 1]) * th
                draw.polygon(list(zip(px, py)), fill=255)
        for patch in ax.patches:
            verts = patch.get_path().vertices
            disp = ax.transData.transform(verts)
            fig_xy = fig.transFigure.inverted().transform(disp)
            px = fig_xy[:, 0] * tw
            py = (1.0 - fig_xy[:, 1]) * th
            draw.polygon(list(zip(px, py)), fill=255)
    return np.array(mask) > 0, scale


def _artist_bbox_px(fig, artist, tw: int, th: int) -> tuple[int, int, int, int]:
    fig.canvas.draw()
    bb = artist.get_window_extent(fig.canvas.get_renderer()).transformed(fig.transFigure.inverted())
    x0 = int(max(0, bb.x0 * tw))
    x1 = int(min(tw, bb.x1 * tw))
    y0 = int(max(0, (1 - bb.y1) * th))
    y1 = int(min(th, (1 - bb.y0) * th))
    return x0, y0, x1, y1


def ui_overlaps_land(r: DailyMapRenderer, *, include_legend: bool = False) -> dict[str, bool]:
    """Dynamic UI vs district pixels. Legend inset is fixed on-map (parity-approved); skip by default."""
    mask, _ = _land_mask_lowres(r)
    th, tw = mask.shape
    items = {
        "stats_line1": r.stats_line1,
        "stats_line2": r.stats_line2,
        "title": r.title,
        "footer": r.foot,
    }
    if include_legend:
        items = {"legend": r.legend_ax, **items}
    out: dict[str, bool] = {}
    for name, art in items.items():
        x0, y0, x1, y1 = _artist_bbox_px(r.fig, art, tw, th)
        if x1 <= x0 or y1 <= y0:
            out[name] = False
            continue
        out[name] = bool(mask[y0:y1, x0:x1].any())
    return out
