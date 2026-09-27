"""Frozen-layout render engine (legacy draw + fast Pillow save)."""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image

from rainfall.config import load_config, resolve_path
from rainfall.render_daily import DailyMapRenderer


def save_figure_pillow(fig, path: Path, dpi: int, *, quantize: bool = False) -> dict[str, Any]:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor="white", pad_inches=0.05)
    buf.seek(0)
    im = Image.open(buf).convert("RGB")
    if quantize:
        im = im.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).convert("RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.png")
    im.save(tmp, format="PNG", compress_level=1, optimize=False)
    tmp.replace(path)
    return {"size": im.size, "file_kb": path.stat().st_size / 1024}


class FrozenRenderer:
    """Build figure once per process; update data + text per date."""

    def __init__(self, cfg: dict | None = None, geom=None) -> None:
        from rainfall.render_geom_cache import load_geometry_cached

        self.cfg = cfg or load_config()
        self.geom = geom or load_geometry_cached(self.cfg)
        self._r = DailyMapRenderer(cfg=self.cfg, geom=self.geom)
        self.dpi = self._r.dpi

    def render_date(self, date: pd.Timestamp, out: Path, *, quantize: bool = False) -> dict[str, Any]:
        cols = ["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std", "qc_isolated_extreme"]
        day = pd.read_parquet(
            resolve_path(self.cfg["paths"]["processed_enriched"]),
            filters=[("date", "=", date)],
            columns=cols,
        )
        t0 = time.perf_counter()
        dp = self._r.draw_date(date, day)
        t_draw = time.perf_counter() - t0
        t1 = time.perf_counter()
        meta = save_figure_pillow(self._r.fig, out, self.dpi, quantize=quantize)
        t_save = time.perf_counter() - t1
        meta.update(
            {
                "date": str(date.date()),
                "seconds_draw": t_draw,
                "seconds_save": t_save,
                "seconds_total": t_draw + t_save,
                "n_districts_with_data": len(dp.shp_mm),
                "n_no_data": sum(1 for v in dp.shp_class.values() if v < 0),
                "n_parent_value": dp.n_parent,
                "n_excluded_suspect": dp.n_excluded_suspect,
                "n_heavy": int(sum(1 for v in dp.shp_mm.values() if v >= 64.5)),
            }
        )
        if dp.shp_mm:
            import numpy as np

            areas = {sid: self.geom.area_by_shp.get(sid, 0) for sid in dp.shp_mm}
            vals = pd.Series(dp.shp_mm)
            w = pd.Series(areas).reindex(vals.index).fillna(0)
            if w.sum() > 0:
                meta["area_weighted_mean_mm"] = float(np.average(vals, weights=w))
            else:
                meta["area_weighted_mean_mm"] = float(vals.mean())
            meta["min_mm"] = float(vals.min())
            meta["max_mm"] = float(vals.max())
            sid_max = int(vals.idxmax())
            grow = self.geom.gdf[self.geom.gdf["shp_id"] == sid_max]
            if len(grow):
                meta["wettest_district"] = f"{grow['district_name'].iloc[0]}, {grow['state_name'].iloc[0]}"
            meta["wettest_mm"] = float(vals.max())
        return meta
