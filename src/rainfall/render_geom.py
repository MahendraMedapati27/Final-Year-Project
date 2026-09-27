"""Shared geometry prep for daily maps (P2/P3)."""



from __future__ import annotations



from dataclasses import dataclass, field



import geopandas as gpd

import numpy as np

import pandas as pd

from shapely import set_precision

from shapely.ops import unary_union



from rainfall.config import load_config, resolve_path

from rainfall.polygon_paths import explode_polygon_paths
from rainfall.render import explode_polygons

_CACHED_GEOM = None





@dataclass

class RenderGeometry:

    gdf: gpd.GeoDataFrame

    outline: gpd.GeoDataFrame

    paths: list

    paths_with_holes: list

    part_to_shp: np.ndarray

    shp_ids: np.ndarray

    pg_by_shp: dict[int, int]

    resolution_by_shp: dict[int, str]

    state_boundary: gpd.GeoSeries

    outside_geom: object

    mainland_mask_shp: np.ndarray

    an_shp_ids: np.ndarray

    ld_shp_ids: np.ndarray

    area_by_shp: dict[int, float]





def _dissolved_state_boundaries(districts: gpd.GeoDataFrame) -> gpd.GeoSeries:

    d = districts.copy()

    d["geometry"] = d.geometry.apply(lambda g: set_precision(g, grid_size=1e-6) if g is not None else g)

    dissolved = d.dissolve(by="state_name", as_index=False)

    lines = dissolved.boundary

    return lines





def load_render_geometry(cfg: dict | None = None, *, use_cache: bool = True) -> RenderGeometry:
    global _CACHED_GEOM
    cfg = cfg or load_config()
    if use_cache and _CACHED_GEOM is not None and hasattr(_CACHED_GEOM, "paths_with_holes"):
        return _CACHED_GEOM
    _CACHED_GEOM = None

    gdf = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="districts")

    outline = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="india_outline")

    poly_map = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))

    pg_by_shp = poly_map.set_index("shp_id")["paint_group_uid"].astype(int).to_dict()

    resolution_by_shp = poly_map.set_index("shp_id")["resolution"].astype(str).to_dict()



    paths, part_to_shp, shp_ids = explode_polygons(gdf)
    paths_with_holes, _, _ = explode_polygon_paths(gdf)

    ea = gdf.to_crs("+proj=aea +lat_1=12 +lat_2=28 +lat_0=20 +lon_0=80 +datum=WGS84 +units=m")

    area_by_shp = dict(zip(gdf["shp_id"].astype(int), (ea.geometry.area / 1e6).values))



    district_union = unary_union(gdf.geometry)

    outside = outline.geometry.iloc[0].difference(district_union)



    state_boundary = _dissolved_state_boundaries(gdf)



    # Andaman & Nicobar vs Lakshadweep (mainland excludes both for tight map)

    st = gdf["state_name"].astype(str)

    an = gdf[st.str.contains("Andaman", case=False, na=False)]["shp_id"].astype(int).values

    ld = gdf[st.str.contains("Lakshadweep", case=False, na=False)]["shp_id"].astype(int).values

    an_set, ld_set = set(an), set(ld)

    mainland_mask = np.array([int(s) not in an_set and int(s) not in ld_set for s in part_to_shp])



    geom = RenderGeometry(
        gdf=gdf,

        outline=outline,

        paths=paths,

        paths_with_holes=paths_with_holes,

        part_to_shp=part_to_shp,

        shp_ids=shp_ids,

        pg_by_shp=pg_by_shp,

        resolution_by_shp=resolution_by_shp,

        state_boundary=state_boundary,

        outside_geom=outside,

        mainland_mask_shp=mainland_mask,

        an_shp_ids=an,

        ld_shp_ids=ld,

        area_by_shp=area_by_shp,
    )
    if use_cache:
        _CACHED_GEOM = geom
    return geom

