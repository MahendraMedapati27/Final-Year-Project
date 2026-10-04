# Code layout

## `src/rainfall/` — Python package

| Area | Modules | Role |
|------|---------|------|
| **CLI** | `cli.py`, `__main__.py` | Typer commands: ingest, geo, clean, render, … |
| **Config** | `config.py` | Load `config/config.yaml`, resolve paths |
| **Ingest & audit** | `io.py`, `schema.py`, `audit.py` | CSV → parquet, portal audit |
| **Geometry** | `geo.py`, `crosswalk.py`, `paint_groups.py`, `simplify_geo.py`, `names.py` | Boundaries, name match, paint groups |
| **Clean & enrich** | `m3_clean.py`, `m3_finalize.py`, `dedupe.py`, `features.py`, `hydrology_matrix.py`, `extremes.py` | Dedupe, enrich, `daily_actual_mm_map` |
| **Render** | `render_daily.py`, `render_engine.py`, `render_pool.py`, `render_geom.py`, `render_geom_cache.py`, `render_layout.py`, `frozen_layout.py`, `palette_lab.py`, `classes.py` | Frozen choropleth engine |
| **Legacy / trial** | `render.py` | Matrix build + early trial render (CLI `render`) |
| **QC & gates** | `gates.py`, `verify.py`, `p1_gate.py`, `p1b.py`, `jjas_sanity.py`, … | Development gates and reports |
| **Verify helpers** | `verify_matrix.py`, `map_stats_independent.py` | Used by `scripts/verify/*` |

## `config/`

`config.yaml`, `name_aliases.csv`, `manual_overrides.csv`

## `data/`

Raw CSV, interim parquet, processed enriched parquet, geometry GPKG (see `.gitignore` for large generated paths).

## `outputs/`

Maps, tables, reports, figures (mostly generated; not all committed).

## `tests/`

Pytest suite; `test_render_p2.py` and layout tests use the frozen renderer.
