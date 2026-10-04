# SECTION 15 — COVERAGE CHECK AND CODEBASE AUDIT

---

## 15.1 Codebase Coverage Verification Table

To guarantee that no module, configuration file, or data artifact was overlooked, below is the exhaustive coverage checklist:

| File / Folder Path | Type | Documented? | Primary Section | Notes & Verification |
| :--- | :--- | :---: | :---: | :--- |
| `ASSUMPTIONS.md` | Markdown Doc | **Yes** | Sec 0, 3, 5, 10 | Real-world discrepancies (735 vs 772, 288 gap days, 0.25% SOI gap). |
| `README.md` | Markdown Doc | **Yes** | Sec 1, 9 | Setup, environment installation, and execution quickstart. |
| `pyproject.toml` | Build Config | **Yes** | Sec 1 | Package metadata, dependencies, and entry point definitions. |
| `requirements.txt` | Dependency File | **Yes** | Sec 1, 9 | Pinned third-party Python packages. |
| `config/config.yaml` | Master Config | **Yes** | Sec 2 | System paths, audit bounds, hydrology thresholds, and map styling. |
| `config/manual_overrides.csv` | Crosswalk Config | **Yes** | Sec 2, 4.7, 5 | Explicit polygon overrides (Bengaluru Urban/Rural, Paschim/Purba Medinipur). |
| `config/name_aliases.csv` | Alias Config | **Yes** | Sec 2, 4.5, 5 | 136 state/district phonetic and historical alias mappings. |
| `data/raw/dataset_full.csv` | Raw Data | **Yes** | Sec 0, 3, 12 | 1,320,770 raw rows, 25 columns (213 MB). |
| `data/interim/raw_full.parquet` | Interim Data | **Yes** | Sec 0, 3 | Standardized Parquet file (12.3 MB). |
| `data/geo/districts_master.gpkg` | GIS Layer | **Yes** | Sec 0, 5 | 785 LGD district polygons in EPSG:4326 (86.9 MB). |
| `data/geo/candidates/india-soi.geojson` | GIS Boundary | **Yes** | Sec 0, 5, 8 | Survey of India official national outer boundary (11.8 MB). |
| `data/processed/district_crosswalk.csv` | Crosswalk | **Yes** | Sec 4.7, 5, 6 | 735 dataset districts mapped to polygon IDs. |
| `data/processed/paint_group_polygons.csv` | Paint Group | **Yes** | Sec 4.8, 5, 6 | 785 polygons mapped to 783 paint groups. |
| `data/processed/rainfall_enriched.parquet` | Master Data | **Yes** | Sec 4.10, 6, 12 | 1,274,184 rows $\times$ 98 columns (34.78 MB). |
| `data/processed/render_matrix.npz` | Render Matrix | **Yes** | Sec 4.10, 6, 8 | $[1800 \times 783]$ NumPy array for instant map color lookups. |
| `src/rainfall/config.py` | Python Source | **Yes** | Sec 4.2 | Path resolution and YAML loader. |
| `src/rainfall/io.py` | Python Source | **Yes** | Sec 4.3 | Regex header mapping, type downcasting, and PyArrow Parquet writer. |
| `src/rainfall/audit.py` | Python Source | **Yes** | Sec 4.4 | Statistical auditing and guarded departure formula. |
| `src/rainfall/names.py` | Python Source | **Yes** | Sec 4.5 | String normalization and alias dictionary engine. |
| `src/rainfall/geo.py` | Python Source | **Yes** | Sec 4.6, 5 | GIS geometry loader, topology repair (`buffer(0)`), and CRS transforms. |
| `src/rainfall/crosswalk.py` | Python Source | **Yes** | Sec 4.7, 5 | Multi-pass Hungarian matching engine. |
| `src/rainfall/paint_groups.py` | Python Source | **Yes** | Sec 4.8, 5 | Spatial containment for split parent-child districts. |
| `src/rainfall/dedupe.py` | Python Source | **Yes** | Sec 4.9 | Vectorized duplicate resolution with Queen spatial neighbors. |
| `src/rainfall/extremes.py` | Python Source | **Yes** | Sec 4.9, 6 | Spatial anomaly inspector for rainfall readings $>500$ mm. |
| `src/rainfall/hydrology_matrix.py` | Python Source | **Yes** | Sec 4.10, 6 | 2D NumPy rolling sum engine (3d/7d/30d), monsoon sums, and spells. |
| `src/rainfall/classes.py` | Python Source | **Yes** | Sec 4.11 | Official IMD intensity bins and departure classifications. |
| `src/rainfall/palette_lab.py` | Python Source | **Yes** | Sec 4.11, 8 | CIELAB perceptual uniformity and colorblindness simulator. |
| `src/rainfall/render_geom.py` | Python Source | **Yes** | Sec 4.12, 8 | Exploded polygon coordinate data structures. |
| `src/rainfall/render_geom_cache.py` | Python Source | **Yes** | Sec 4.12, 7 | Geometry cache manager (`geometry.pkl`). |
| `src/rainfall/render_daily.py` | Python Source | **Yes** | Sec 4.12, 8 | Complete Matplotlib cartographic renderer (insets, cards, legend). |
| `src/rainfall/render_engine.py` | Python Source | **Yes** | Sec 4.12 | Frozen renderer with direct Pillow Zlib image compression. |
| `src/rainfall/render_pool.py` | Python Source | **Yes** | Sec 4.12, 9 | RAM-aware multiprocessing worker pool coordinator. |
| `src/rainfall/m3_clean.py` | Python Source | **Yes** | Sec 4.9, 4.10 | Master cleaning & enrichment pipeline coordinator. |
| `src/rainfall/m3_finalize.py` | Python Source | **Yes** | Sec 6, 8 | Aggregation table generator (state, national, seasonal). |
| `src/rainfall/schema.py` | Python Source | **Yes** | Sec 6 | Master schema definition for all 98 enriched columns. |
| `src/rainfall/gates.py` | Python Source | **Yes** | Sec 7, 8 | Pipeline quality gate checkers and metric verifiers. |
| `src/rainfall/verify.py` | Python Source | **Yes** | Sec 7, 9 | Automated integrity gate verifying row counts and column completeness. |
| `src/rainfall/cli.py` | Python Source | **Yes** | Sec 4.1, 9 | Typer command-line interface and thread-limit manager. |
| `scripts/render/build_geometry_cache.py` | Script | **Yes** | Sec 7, 9 | Builds `outputs/render_cache/<hash>/geometry.pkl`. |
| `scripts/render/render_all_daily_maps.py` | Script | **Yes** | Sec 7, 8, 9 | Production batch renderer for all 1,800 daily maps. |
| `scripts/verify/qa_all_maps.py` | Script | **Yes** | Sec 7, 8, 9 | Master QA audit suite verifying PNG outputs and manifest. |
| `outputs/maps/daily_actual/manifest.csv` | Output Manifest | **Yes** | Sec 8 | Auditable map inventory detailing daily stats for every rendered date. |
| `outputs/reports/data_audit_full.md` | Output Report | **Yes** | Sec 3, 8 | Comprehensive statistical audit comparing raw data against portal targets. |
| `outputs/reports/data_dictionary.md` | Output Report | **Yes** | Sec 6, 8 | Auto-generated schema dictionary defining all 98 attributes. |
| `tests/*` | Pytest Suite | **Yes** | Sec 7 | Automated unit and integration test suite (8 test modules). |

---

## 15.2 Intentional Exclusions (With Technical Justifications)

1. **`src/rainfall/clean.py`:** Legacy M1 cleaning prototype. Superseded by `m3_clean.py` and `dedupe.py` which implement vectorized multi-tier spatial deduplication and NumPy matrix math without memory crashes.
2. **`outputs/render_cache/<hash>/geometry.pkl` (201 MB):** Binary pickle container of pre-built Matplotlib paths; generated on demand via `build_geometry_cache.py`.
3. **`data/interim/raw_sample.parquet` & `dataset_sample_5k.csv`:** 5,000-row testing slices; identical in schema and logic to the full dataset.

<!-- SECTION 15 COMPLETE -->
