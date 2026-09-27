"""P1.4: district centroid inside dataset state polygon."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from rainfall.config import load_config, resolve_path
from rainfall.names import normalize_state


def run_spatial_validation() -> pd.DataFrame:
    cfg = load_config()
    cw = pd.read_csv(resolve_path(cfg["paths"]["crosswalk"]))
    dist = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="districts")
    states = gpd.read_file(resolve_path(cfg["paths"]["geo_districts"]), layer="states")

    dist = dist.to_crs(4326)
    states = states.to_crs(4326)
    states["state_key"] = states["state_name"].map(normalize_state)
    st_by_key = states.set_index("state_key")

    rows = []
    for _, r in cw.dropna(subset=["shp_id"]).iterrows():
        sid = int(r["shp_id"])
        drow = dist[dist["shp_id"] == sid]
        if drow.empty:
            continue
        geom = drow.geometry.iloc[0]
        pt = geom.representative_point()
        sk = normalize_state(r["dataset_state"])
        if sk not in st_by_key.index:
            inside = False
        else:
            st_geom = st_by_key.loc[sk, "geometry"]
            if hasattr(st_geom, "iloc"):
                st_geom = st_geom.iloc[0]
            inside = bool(st_geom.contains(pt))
        rows.append(
            {
                "dataset_state": r["dataset_state"],
                "dataset_district": r["dataset_district"],
                "shp_id": sid,
                "lgd_name": drow["district_name"].iloc[0],
                "centroid_lon": pt.x,
                "centroid_lat": pt.y,
                "inside_state": inside,
            }
        )
    rep = pd.DataFrame(rows)
    fails = rep[~rep["inside_state"]]
    rep.to_csv(resolve_path("outputs/tables/spatial_centroid_validation.csv"), index=False)
    fails.to_csv(resolve_path("outputs/tables/spatial_centroid_failures.csv"), index=False)
    return rep
