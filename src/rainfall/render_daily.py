"""P2/P3 daily choropleth renderer (layout v2, map column, insets)."""



from __future__ import annotations



import logging

import time

from dataclasses import dataclass

from pathlib import Path

from typing import Any



import geopandas as gpd

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

import numpy as np

import pandas as pd

from matplotlib.collections import PolyCollection

from matplotlib.colors import BoundaryNorm, ListedColormap

from matplotlib.patches import Patch, Rectangle

from matplotlib.transforms import Bbox



from rainfall.classes import INTENSITY_LABELS, daily_intensity_class

from rainfall.config import load_config, resolve_path

from rainfall.palette_lab import CLASS_RANGES, NODATA_FACE, OUTSIDE_FILL, PALETTE_HEX

from rainfall.render_geom import RenderGeometry, load_render_geometry



logger = logging.getLogger(__name__)



HATCH_NODATA = {"facecolor": NODATA_FACE, "edgecolor": "#666666", "hatch": "///", "linewidth": 0.2}


def _display_name(raw: str) -> str:
    s = str(raw).strip()
    if not s:
        return s
    if s.isupper():
        return s.title()
    return s



@dataclass

class DayPaint:

    shp_class: dict[int, int]

    shp_mm: dict[int, float]

    n_parent: int

    n_excluded_suspect: int

    area_km2_data: float

    area_km2_nodata: float

    area_km2_total: float





def _day_paint(

    geom: RenderGeometry,

    day: pd.DataFrame,

    mm_col: str = "daily_actual_mm_map",

) -> DayPaint:

    shp_class: dict[int, int] = {}

    shp_mm: dict[int, float] = {}

    n_parent = 0

    n_excl = 0

    area_data = 0.0

    area_nodata = 0.0

    by_pg = day.set_index("paint_group_uid")

    for sid in np.unique(geom.part_to_shp):

        sid = int(sid)

        pg = geom.pg_by_shp.get(sid, -1)

        area = geom.area_by_shp.get(sid, 0.0)
        res = geom.resolution_by_shp.get(sid, "")

        if pg not in by_pg.index or pd.isna(by_pg.loc[pg, mm_col]):

            shp_class[sid] = -1

            area_nodata += area

            continue

        mm = float(by_pg.loc[pg, mm_col])

        shp_mm[sid] = mm

        _, c = daily_intensity_class(pd.Series([mm]))

        shp_class[sid] = int(c.iloc[0])

        area_data += area

        if str(res).startswith("child_of"):

            n_parent += 1

        if "qc_isolated_extreme" in by_pg.columns and bool(by_pg.loc[pg, "qc_isolated_extreme"]):

            n_excl += 1

    total = area_data + area_nodata

    return DayPaint(shp_class, shp_mm, n_parent, n_excl, area_data, area_nodata, total)





class DailyMapRenderer:

    """Figure built once; update arrays/text per date (P3.2)."""



    def __init__(self, cfg: dict | None = None, geom: RenderGeometry | None = None) -> None:

        self.cfg = cfg or load_config()

        rc = self.cfg["render"]

        self.dpi = int(rc.get("dpi", 150))

        self.fw = float(rc.get("figure_width_in", 10))

        self.fh = float(rc.get("figure_height_in", 11))

        self.geom = geom or load_render_geometry(self.cfg)

        self.cmap = ListedColormap(PALETTE_HEX)

        self.norm = BoundaryNorm(np.arange(-0.5, 7.5, 1), self.cmap.N)

        self._build_figure(rc)



    def _build_figure(self, rc: dict) -> None:

        self.fig = plt.figure(figsize=(self.fw, self.fh), dpi=self.dpi)

        self.fig.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.11)

        self.ax_main = self.fig.add_axes([0.06, 0.15, 0.88, 0.74])

        g = self.geom

        if not g.outside_geom.is_empty:

            gpd.GeoSeries([g.outside_geom], crs=g.gdf.crs).plot(

                ax=self.ax_main, color=OUTSIDE_FILL, edgecolor="none", zorder=0

            )



        g.gdf.plot(ax=self.ax_main, color=OUTSIDE_FILL, edgecolor="none", zorder=1, rasterized=True)

        self.pc_nd = PolyCollection([], **HATCH_NODATA, zorder=2)

        self.pc_main = PolyCollection(

            [],

            cmap=self.cmap,

            norm=self.norm,

            edgecolor="#444444",

            linewidth=float(rc.get("district_linewidth", 0.25)),

            joinstyle="round",

            zorder=3,
            rasterized=True,
        )

        self.ax_main.add_collection(self.pc_nd)

        self.ax_main.add_collection(self.pc_main)

        g.state_boundary.plot(ax=self.ax_main, color="none", edgecolor="#404040", linewidth=float(rc.get("state_linewidth", 0.5)), alpha=0.85, zorder=4)

        g.outline.boundary.plot(ax=self.ax_main, color="#101010", linewidth=float(rc.get("outline_linewidth", 0.6)), zorder=5)



        self.ax_main.set_xlim(68, 97)

        self.ax_main.set_ylim(8, 37)

        self.ax_main.set_aspect("equal")

        self.ax_main.axis("off")



        self.title = self.fig.suptitle("", fontsize=12, y=0.97)

        self.stats_line1 = self.fig.text(
            0.5, 0.075, "", ha="center", va="center", fontsize=7, bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.92)
        )
        self.stats_line2 = self.fig.text(0.5, 0.038, "", ha="center", va="center", fontsize=6.5, bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.92))
        self.foot = self.fig.text(0.5, 0.008, "", ha="center", fontsize=6.5)

        leg_box = rc.get("legend_inset_axes", [0.56, 0.03, 0.42, 0.30])
        self.legend_ax = self.ax_main.inset_axes(leg_box)
        self.legend_ax.set_zorder(10)
        self.legend_ax.patch.set_alpha(0.92)
        self.legend_ax.axis("off")

        self._legend_patches = [

            Patch(facecolor=PALETTE_HEX[i], edgecolor="#555", label=f"{INTENSITY_LABELS[i]} {CLASS_RANGES[i]}")

            for i in range(7)

        ]

        self._legend_patches.append(Patch(facecolor=NODATA_FACE, hatch="///", edgecolor="#666", label="No data"))

        self.legend_obj = self.legend_ax.legend(handles=self._legend_patches, loc="upper left", fontsize=6, title="Daily rainfall (mm)", framealpha=0.92)



    def _paths_for_shps(self, shp_set: set[int]) -> tuple[list, list, list]:

        paths_v, paths_n, vals = [], [], []

        for i, sid in enumerate(self.geom.part_to_shp):

            sid = int(sid)

            if sid not in shp_set:

                continue

            paths_v.append(self.geom.paths[i])

            vals.append(self._current_class.get(sid, -1))

        for i, sid in enumerate(self.geom.part_to_shp):

            sid = int(sid)

            if sid not in shp_set:

                continue

            c = self._current_class.get(sid, -1)

            if c < 0:

                paths_n.append(self.geom.paths[i])

        return paths_v, paths_n, vals



    _current_class: dict[int, int]



    def draw_date(self, date: pd.Timestamp, day_df: pd.DataFrame) -> DayPaint:

        dp = _day_paint(self.geom, day_df)

        self._current_class = dp.shp_class

        all_on_map = set(int(s) for s in self.geom.part_to_shp)

        paths_v, paths_n, vals = self._paths_for_shps(all_on_map)

        self.pc_nd.set_paths(paths_n)

        self.pc_nd.set_visible(bool(paths_n))

        valid = [v for v in vals if v >= 0]

        self.pc_main.set_paths([p for p, v in zip(paths_v, vals) if v >= 0])

        self.pc_main.set_array(np.array(valid, dtype=float) if valid else np.array([]))

        self.pc_main.set_visible(bool(valid))



        subtitle = f"Daily rainfall (mm) — {date.strftime('%A, %d %B %Y')}"

        self.title.set_text(f"District-wise Actual Rainfall over India\n{subtitle}")



        counts = pd.Series([v for v in dp.shp_class.values() if v >= 0]).value_counts().sort_index()

        handles = []

        for i, lab in enumerate(INTENSITY_LABELS):

            n = int(counts.get(i, 0))

            handles.append(Patch(facecolor=PALETTE_HEX[i], edgecolor="#555", label=f"{lab} {CLASS_RANGES[i]} ({n})"))

        nd_n = sum(1 for v in dp.shp_class.values() if v < 0)

        nd_pct = 100.0 * dp.area_km2_nodata / dp.area_km2_total if dp.area_km2_total else 0

        handles.append(Patch(facecolor=NODATA_FACE, hatch="///", edgecolor="#666", label=f"No data ({nd_n}, {nd_pct:.1f}% area)"))

        self.legend_ax.clear()

        self.legend_ax.axis("off")

        self.legend_obj = self.legend_ax.legend(handles=handles, loc="upper left", fontsize=6, title="Daily rainfall (mm)", framealpha=0.92)



        mm_s = pd.Series(dp.shp_mm)

        w = pd.Series({sid: self.geom.area_by_shp.get(sid, 0) for sid in dp.shp_mm}).reindex(mm_s.index).fillna(0)

        if len(mm_s) and w.sum() > 0:
            wmean = float(np.average(mm_s, weights=w))
        elif len(mm_s):
            wmean = float(mm_s.mean())
        else:
            wmean = float("nan")

        wet = ""

        if len(mm_s):

            sid_max = int(mm_s.idxmax())

            grow = self.geom.gdf[self.geom.gdf["shp_id"] == sid_max]

            if len(grow):

                st = _display_name(grow["state_name"].iloc[0])

                dist = _display_name(grow["district_name"].iloc[0])

            else:

                row = day_df[day_df["paint_group_uid"] == self.geom.pg_by_shp.get(sid_max)]

                st = _display_name(row["state_std"].iloc[0]) if len(row) and "state_std" in row.columns else "?"

                dist = _display_name(row["district_std"].iloc[0]) if len(row) and "district_std" in row.columns else "?"

            wet = f"  Wettest: {dist}, {st} ({mm_s.max():.1f} mm)"

        excl = f"  Excluded as suspect: {dp.n_excluded_suspect}." if dp.n_excluded_suspect else ""

        line1 = (
            f"Districts With Data: {len(mm_s)}  ·  Area-Weighted Mean: {wmean:.1f} mm"
            f"  ·  ≥64.5 mm: {(mm_s >= 64.5).sum() if len(mm_s) else 0}"
            f"  ·  Parent Value: {dp.n_parent}"
        )
        line2 = (wet.strip() + excl).strip(" ·") if wet or excl else ""
        self.stats_line1.set_text(line1)
        self.stats_line2.set_text(line2 if line2 else " ")

        fn = self.cfg["render"].get("paint_group_footnote", "")
        cap = "Hatched districts have no reported value."
        self.foot.set_text(f"Data: IMD/MoES via NDAP · Boundaries: LGD/india-geodata 2026 · {cap} · {fn}")

        return dp



    def _draw_inset(self, ax, shp_set: set[int]) -> None:

        sub = self.geom.gdf[self.geom.gdf["shp_id"].isin(shp_set)]

        if sub.empty:

            return

        paths_v, paths_n, vals = self._paths_for_shps(shp_set)

        if paths_n:

            ax.add_collection(PolyCollection(paths_n, **HATCH_NODATA, zorder=2))

        if paths_v and any(v >= 0 for v in vals):

            pc = PolyCollection(

                [p for p, v in zip(paths_v, vals) if v >= 0],

                cmap=self.cmap,

                norm=self.norm,

                edgecolor="#444",

                linewidth=0.2,

                zorder=3,

            )

            pc.set_array(np.array([v for v in vals if v >= 0], dtype=float))

            ax.add_collection(pc)

        sub.boundary.plot(ax=ax, linewidth=0.2, edgecolor="#444", zorder=4)

        minx, miny, maxx, maxy = sub.total_bounds

        ld_set = set(int(x) for x in self.geom.ld_shp_ids)
        is_ld = bool(shp_set) and shp_set.issubset(ld_set)
        pad = 0.06 if is_ld else 0.35
        lw = 0.75 if is_ld else 0.25

        ax.set_xlim(minx - pad, maxx + pad)

        ax.set_ylim(miny - pad, maxy + pad)

        ax.set_aspect("equal")
        for coll in ax.collections:
            if hasattr(coll, "set_linewidth"):
                coll.set_linewidth(lw)



    def save(self, path: Path) -> dict[str, Any]:

        path.parent.mkdir(parents=True, exist_ok=True)

        t0 = time.perf_counter()

        self.fig.savefig(path, dpi=self.dpi, facecolor="white", pad_inches=0.05)

        elapsed = time.perf_counter() - t0
        draw_s = 0.0
        save_s = elapsed

        from PIL import Image



        im = Image.open(path)

        return {

            "path": str(path),

            "size": im.size,

            "dpi": self.dpi,

            "seconds_draw": draw_s,

            "seconds_save": save_s,

            "seconds_total": elapsed,

            "file_kb": path.stat().st_size / 1024,

        }





def northern_grey_report(geom: RenderGeometry, dates: list[pd.Timestamp], enriched_path: str) -> pd.DataFrame:

    """P2.5 / A3: identify large northern grey polygons and values."""

    rows = []

    g = geom.gdf

    north = g[g.geometry.centroid.y > 34]

    cols = ["date", "paint_group_uid", "daily_actual_mm_map", "daily_actual_mm", "state_std", "district_std"]

    import pyarrow.parquet as pq



    schema = pq.read_schema(enriched_path).names

    cols = [c for c in cols if c in schema]

    for d in dates:

        day = pd.read_parquet(enriched_path, filters=[("date", "=", d)], columns=cols)

        by_pg = day.set_index("paint_group_uid")

        for _, row in north.iterrows():

            sid = int(row["shp_id"])

            pg = geom.pg_by_shp.get(sid, -1)

            mm = np.nan

            if pg in by_pg.index:

                mm = by_pg.loc[pg, "daily_actual_mm_map"] if "daily_actual_mm_map" in by_pg.columns else by_pg.loc[pg, "daily_actual_mm"]

            rows.append(

                {

                    "date": str(d.date()),

                    "shp_id": sid,

                    "state": row.get("state_name"),

                    "district": row.get("district_name"),

                    "resolution": geom.resolution_by_shp.get(sid),

                    "daily_actual_mm_map": mm,

                    "is_outside_fill": pg <= 0,

                }

            )

    return pd.DataFrame(rows)





def render_one_date(date: pd.Timestamp, out_path: Path, cfg: dict | None = None) -> dict[str, Any]:

    cfg = cfg or load_config()

    cols = ["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std", "qc_isolated_extreme"]

    day = pd.read_parquet(resolve_path(cfg["paths"]["processed_enriched"]), filters=[("date", "=", date)], columns=cols)

    r = DailyMapRenderer(cfg=cfg)

    r.draw_date(date, day)

    meta = r.save(out_path)

    meta["date"] = str(date.date())

    return meta





def run_p2_trials(cfg: dict | None = None) -> list[dict]:

    cfg = cfg or load_config()

    from rainfall.render import wettest_day_2022_2025



    en = pd.read_parquet(resolve_path(cfg["paths"]["processed_enriched"]), columns=["date", "daily_actual_mm_map", "daily_actual_mm"])

    d_dense = pd.Timestamp("2022-07-26")
    if d_dense not in en["date"].values:
        d_dense = wettest_day_2022_2025(en)

    dates = [pd.Timestamp("2026-09-19"), pd.Timestamp("2025-05-31"), d_dense]

    out_dir = resolve_path("outputs/maps/p2_trial")

    results = []

    r = DailyMapRenderer(cfg=cfg)

    cols = ["date", "paint_group_uid", "daily_actual_mm_map", "state_std", "district_std", "qc_isolated_extreme"]

    for d in dates:

        day = pd.read_parquet(resolve_path(cfg["paths"]["processed_enriched"]), filters=[("date", "=", d)], columns=cols)

        dp = r.draw_date(d, day)

        p = out_dir / f"rainfall_actual_{d.date()}.png"

        meta = r.save(p)

        meta["legend_counts"] = {INTENSITY_LABELS[i]: int((pd.Series(list(dp.shp_class.values())) == i).sum()) for i in range(7)}

        meta["n_data_districts"] = len(dp.shp_mm)

        results.append(meta)

    return results

