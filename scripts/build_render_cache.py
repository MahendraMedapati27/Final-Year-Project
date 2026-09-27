"""Build geometry pickle (+ optional raster cache). Main process only."""

from __future__ import annotations

import time

from rainfall.render_geom_cache import ensure_geometry_cache


def main() -> None:
    t0 = time.perf_counter()
    p = ensure_geometry_cache(force=False)
    print("geometry cache:", p, f"{time.perf_counter()-t0:.1f}s")


if __name__ == "__main__":
    main()
