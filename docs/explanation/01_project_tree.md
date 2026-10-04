# SECTION 1 — COMPLETE PROJECT DIRECTORY TREE

---

## 1.1 Complete Verified Directory Tree

Below is the complete directory tree of the repository on disk, excluding temporary virtual environment directories (`.venv`), git internals (`.git`), and bytecode caches (`__pycache__`):

```text
d:\final year project\
├── ASSUMPTIONS.md                              # Core architectural decisions, audit discrepancies & gate logs
├── Makefile                                    # Quick developer shortcuts (test, clean, etc.)
├── README.md                                   # High-level overview, setup guide, and execution commands
├── pyproject.toml                              # Python package metadata and build definitions (india_rainfall)
├── requirements.txt                            # Pinned Python package dependencies
├── config/                                     # Master configuration files and manual adjustments
│   ├── config.yaml                             # Main system settings (paths, thresholds, styles, colors)
│   ├── manual_overrides.csv                    # Explicit district-to-polygon ID overrides (e.g. Bengaluru Urban/Rural)
│   └── name_aliases.csv                        # Known spelling variations between weather portal & map boundaries
├── data/                                       # Data storage across different lifecycle stages
│   ├── raw/                                    # Untouched raw source CSV files from portal
│   │   ├── dataset_sample_5k.csv               # 5,000-row sample for fast unit testing and development (1.09 MB)
│   │   └── dataset_full.csv                    # Complete NDAP/IMD weather dataset (213.37 MB, 1.32M rows)
│   ├── interim/                                # Standardized Parquet files after ingestion
│   │   ├── raw_sample.parquet                  # Ingested sample dataset (0.14 MB)
│   │   └── raw_full.parquet                    # Ingested full dataset with standardized types (12.29 MB)
│   ├── geo/                                    # Geographic boundary shapefiles, geopackages, and candidates
│   │   ├── districts_master.gpkg               # Primary LGD 2026 district boundary layer (86.96 MB, 785 polygons)
│   │   └── candidates/                         # Alternative candidate boundary files and historical records
│   │       ├── india-soi.geojson               # Official Survey of India (SOI) external boundary outline (11.76 MB)
│   │       ├── datta07/                        # Alternative Datta07 GeoJSON boundaries (74.22 MB)
│   │       ├── historical/                     # Historical administrative district reorganization CSV tables
│   │       │   ├── District_name_changes_1951_to_2021.csv
│   │       │   ├── District_splits_and_carveouts_1951_to_2024.csv
│   │       │   └── New_districts_created_1951_to_2024.csv
│   │       ├── imd/                            # IMD 2024 simplified reference boundary gist (2.05 MB)
│   │       ├── india-geodata/                  # India-geodata Bhuvan, LGD, and SOI district layers (.parquet/.pmtiles)
│   │       └── lgd/                            # Local Government Directory reference code tables
│   └── processed/                              # Cleaned, enriched datasets, crosswalks, and matrix artifacts
│       ├── district_crosswalk.csv              # Mapping of dataset district names to geographic polygon IDs (70 KB)
│       ├── paint_group_polygons.csv            # Mapping of 785 polygons to 783 paint groups (30 KB)
│       ├── rainfall_enriched.parquet           # Master analytical dataset with 98 enriched columns (34.78 MB, 1.27M rows)
│       ├── rainfall_enriched.csv.gz            # Compressed CSV export of enriched master dataset (2.80 MB)
│       ├── render_matrix.npz                   # Compact 2D rendering matrix (1,800 dates x 783 polygons) (1.35 MB)
│       └── checkpoints/                        # Saved intermediate pipeline states
│           ├── deduped.parquet                 # Deduplicated interim dataset (13.92 MB, 1.27M rows)
│           └── enriched_YYYY.parquet           # Year-by-year enriched checkpoint slices
├── docs/                                       # Documentation and reference guides
│   ├── CODE_LAYOUT.md                          # Module responsibility reference table
│   ├── PROJECT_EXPLANATION.md                  # High-level architecture guide (historical starting point)
│   ├── PROJECT_EXPLANATION_FULL.md             # Master documentation index
│   └── explanation/                            # Detailed deep-dive documentation chapters (Sections 0–15)
├── logs/                                       # Execution logs, memory tracking, and error traces
│   ├── clean_memory.jsonl                      # Step-by-step RAM consumption logs during cleaning & enrichment
│   ├── render_progress.log                     # Progress watchdog log during batch map rendering
│   └── render_errors.csv                       # Error log capturing failed dates or rendering crashes
├── outputs/                                    # All generated deliverables produced by the system
│   ├── checkpoints/                            # Gate evaluation JSON files verifying pipeline criteria
│   │   ├── part_a_gate.json                    # Geometry & crosswalk gate results (name agreement, IoU)
│   │   ├── part_b_gate.json                    # Deduplication & enrichment gate results (row counts, RAM)
│   │   ├── part_c_gate.json                    # Trial render gate results
│   │   ├── p5_full_render.json                 # Production render completion metrics (1,800 maps rendered)
│   │   ├── p5_qa.json                          # Full QA audit suite results
│   │   └── verify.json                         # Final schema and row accounting verification
│   ├── maps/                                   # Rendered choropleth daily maps
│   │   ├── daily_actual/                       # Final publication-grade daily maps organized by YYYY/MM/
│   │   │   ├── 2021/ ... 2026/                 # 1,800 high-resolution PNG maps (1500x1650 px @ 150 DPI)
│   │   │   └── manifest.csv                    # Complete map inventory and per-day statistics (10.5 KB)
│   │   ├── reference/                          # Parity reference gold standards (approved_2021-01-31.png, etc.)
│   │   └── trial/                              # Preliminary test render maps
│   ├── render_cache/                           # Pre-computed geometry caches for high-speed rendering
│   │   └── <hash>/                             # Cache folder keyed by render configuration hash
│   │       ├── geometry.meta.json              # Cache metadata, CRS, and timestamp
│   │       └── geometry.pkl                    # Pickled Matplotlib PolyCollections (201.97 MB)
│   ├── reports/                                # Generated Markdown audit reports and summaries
│   │   ├── data_audit_full.md                  # Comprehensive statistical audit of raw dataset vs IMD targets
│   │   ├── data_dictionary.md                  # Complete schema description of all 98 enriched columns
│   │   ├── duplicates_analysis.md              # Detailed breakdown of duplicate key patterns
│   │   ├── district_count_reconciliation.md    # Investigation of 735 dataset keys vs 772 portal districts
│   │   ├── geometry_candidates.md              # Evaluation and scoring of candidate GIS boundary files
│   │   └── unknown_districts.md                # Report on placeholder "Unknown Districts Of India" records
│   └── tables/                                 # Summary tables and analytical aggregations (CSV and Parquet)
│       ├── duplicates_resolved.csv             # Complete audit of all 42,258 resolved duplicate groups (3.37 MB)
│       ├── extreme_values_review.csv           # Manual inspection of rainfall readings exceeding 500 mm
│       ├── missing_days_by_month.csv           # Calendar breakdown of the 288 missing days
│       ├── national_daily.parquet              # Area-weighted national daily average rainfall
│       ├── state_daily.parquet                 # State-level daily rainfall aggregates
│       ├── district_monthly.parquet            # Monthly district rainfall totals
│       ├── district_season.parquet             # Seasonal (JJAS monsoon, winter, etc.) district aggregations
│       └── district_annual.parquet             # Annual district rainfall summaries
├── scripts/                                    # Automated execution, rendering, and QA scripts
│   ├── README.md                               # Explanation of script categories and usage instructions
│   ├── run_python.ps1                          # PowerShell launcher avoiding Windows DLL application control issues
│   ├── benchmarks/                             # Performance measurement scripts (timing_slice_render.py)
│   ├── pipeline/                               # Pipeline orchestration scripts (resume_enrich.py)
│   ├── render/                                 # Map rendering scripts (render_all_daily_maps.py, build_geometry_cache.py)
│   └── verify/                                 # QA, parity, and verification scripts (qa_all_maps.py, data_matrix_check.py)
├── src/rainfall/                               # Core Python library containing all algorithms and business logic
│   ├── __init__.py                             # Package initialization and version definition
│   ├── __main__.py                             # Entry point for `python -m rainfall`
│   ├── aggregates.py                           # Aggregation engine (state/national daily, district monthly/seasonal)
│   ├── audit.py                                # Statistical data auditor and portal reconciliation engine
│   ├── classes.py                              # Official IMD rainfall intensity and departure classification rules
│   ├── clean.py                                # Legacy cleaning module (preserved for reference/comparisons)
│   ├── cli.py                                  # Command-line interface with Typer commands and thread limits
│   ├── config.py                               # Configuration manager and cross-platform path resolver
│   ├── crosswalk.py                            # Multi-pass district-to-polygon matching engine (Hungarian matching)
│   ├── dedupe.py                               # Vectorized duplicate resolution engine using Queen spatial neighbors
│   ├── duplicates.py                           # Duplicate group diagnostic analyzer
│   ├── extremes.py                             # Spatial extreme value inspector (>500 mm anomaly detection)
│   ├── features.py                             # Time-series feature engineering helpers
│   ├── frozen_layout.py                        # Layout hashing and color array conversion utilities
│   ├── gates.py                                # Quality gate verification checks for pipeline stages
│   ├── geo.py                                  # GIS geometry loader, validator, CRS transformer, and Indian outline builder
│   ├── historical_orphans.py                   # Historical split/carveout assignment helper for unmapped child districts
│   ├── hydrology_matrix.py                     # High-performance 2D NumPy hydrology calculation engine
│   ├── io.py                                   # Regex column mapper, PyArrow Parquet writer, and SHA256 manifest logger
│   ├── jjas_sanity.py                          # June–September monsoon national rainfall sanity check
│   ├── m3_clean.py                             # Master cleaning coordinator (deduplication + matrix enrichment)
│   ├── m3_finalize.py                          # Final aggregation exporter and data dictionary generator
│   ├── map_stats_independent.py                # Standalone calculator for map manifest summary statistics
│   ├── memory_log.py                           # Process RAM logger (tracking RSS memory usage)
│   ├── names.py                                # String normalizer (casing, punctuation, aliases)
│   ├── nodata_report.py                        # Missing observation analyzer
│   ├── p1_gate.py                              # Gate script for data integrity, dedupe, and geometry coverage
│   ├── p1b.py                                  # Duplicate reconciliation and unresolvable conflict analyzer
│   ├── paint_groups.py                         # Spatial containment resolver for parent-child split districts
│   ├── palette_lab.py                          # CIELAB color space validator and colorblindness simulator
│   ├── polygon_paths.py                        # Matplotlib path converter for Shapely polygons
│   ├── render.py                               # Trial map renderer and NPZ matrix exporter
│   ├── render_daily.py                         # Complete Matplotlib map layout builder (insets, cards, legend)
│   ├── render_engine.py                        # Frozen map rendering engine with Pillow direct compression
│   ├── render_geom.py                          # Geometry struct container for pre-exploded polygons
│   ├── render_geom_cache.py                    # Geometry cache manager (loading and saving geometry.pkl)
│   ├── render_layout.py                        # Bounding box layout collision detector (preventing text overlaps)
│   ├── render_pool.py                          # RAM-aware multiprocessing worker pool coordinator
│   ├── schema.py                               # Formal schema definitions and column specifications
│   ├── simplify_geo.py                         # Polygon simplification evaluator and benchmark
│   ├── spatial_validate.py                     # Centroid-in-polygon spatial integrity validator
│   ├── unknown_districts.py                    # Diagnostic tool for placeholder "Unknown" districts
│   ├── validate_crosswalk.py                   # Intersection-over-Union (IoU) validator for polygon crosswalk
│   ├── verify.py                               # Verification gate confirming 100% schema and row compliance
│   └── verify_matrix.py                        # Render matrix parity validator
└── tests/                                      # Automated Pytest test suite
    ├── conftest.py                             # Shared Pytest fixtures
    ├── test_cli.py                             # CLI argument parsing and execution tests
    ├── test_frozen_layout_worst_case.py        # Visual layout tests for worst-case data dates
    ├── test_geo.py                             # GIS loading, CRS transformation, and boundary tests
    ├── test_io.py                              # CSV ingestion, regex header mapping, and Parquet I/O tests
    ├── test_m3_full.py                         # End-to-end cleaning, deduplication, and enrichment tests
    ├── test_p1b.py                             # Duplicate rule reconciliation tests
    ├── test_render_p2.py                       # Rendering pipeline and geometry cache tests
    └── test_verify_stats.py                    # Statistical aggregation accuracy tests
```

---

## 1.2 Master Inventory Table

| File / Folder | Type | Purpose | Critical? |
| :--- | :--- | :--- | :--- |
| `config/config.yaml` | YAML Config | Central settings file specifying all paths, audit thresholds, color palettes, and map layout bounds. | **Yes** |
| `config/manual_overrides.csv` | CSV Config | Deterministic overrides mapping tricky district names directly to polygon IDs (fixing swaps like Bengaluru Urban/Rural). | **Yes** |
| `config/name_aliases.csv` | CSV Config | Dictionary mapping 130+ historical, alternate, or misspelled district/state names to canonical map names. | **Yes** |
| `data/raw/dataset_full.csv` | Raw Data | Primary raw meteorological dataset from NDAP/IMD (1,320,770 rows, 25 columns, 213 MB). | **Yes** |
| `data/interim/raw_full.parquet` | Interim Data | Type-standardized, compressed columnar version of raw CSV, parsed in seconds. | **Yes** |
| `data/geo/districts_master.gpkg` | GIS Boundary | Official Local Government Directory (LGD 2026) district polygons (785 polygons in EPSG:4326). | **Yes** |
| `data/geo/candidates/india-soi.geojson` | GIS Boundary | Official Survey of India (SOI) external boundary outline for India. | **Yes** |
| `data/processed/district_crosswalk.csv` | Crosswalk | Linkage table mapping each dataset district name to its corresponding geographic polygon ID. | **Yes** |
| `data/processed/paint_group_polygons.csv` | Crosswalk | Grouping table mapping all 785 polygons to 783 paint groups (resolving parent-child split districts). | **Yes** |
| `data/processed/checkpoints/deduped.parquet` | Processed Data | Cleaned dataset after resolving all 42,258 duplicate groups (1,274,184 rows). | **Yes** |
| `data/processed/rainfall_enriched.parquet` | Processed Data | Master analytical table with 98 columns including rolling sums, monsoon cumulative totals, and spell streaks. | **Yes** |
| `data/processed/render_matrix.npz` | Render Matrix | High-speed NumPy array $[1800 \times 783]$ containing daily rainfall values and category indices for instant map lookup. | **Yes** |
| `src/rainfall/cli.py` | Source Code | Command-line entry point providing subcommands (`ingest`, `audit`, `clean`, `render`, `verify`). | **Yes** |
| `src/rainfall/config.py` | Source Code | Helper module that reads `config.yaml` and resolves OS-independent absolute file paths. | **Yes** |
| `src/rainfall/io.py` | Source Code | Ingestion engine using regular expressions to map raw headers and PyArrow for fast Parquet writing. | **Yes** |
| `src/rainfall/audit.py` | Source Code | Statistical auditing engine comparing raw distributions against government portal targets. | **Yes** |
| `src/rainfall/names.py` | Source Code | String normalization engine handling casing, punctuation, and alias lookups. | **Yes** |
| `src/rainfall/geo.py` | Source Code | Spatial engine for loading GIS geometries, validating topologies, and reprojecting CRS. | **Yes** |
| `src/rainfall/crosswalk.py` | Source Code | Multi-pass name matcher combining exact match, normalized match, fuzzy RapidFuzz, and Hungarian optimization. | **Yes** |
| `src/rainfall/paint_groups.py` | Source Code | Spatial intersection engine resolving newly carved districts to parent weather records. | **Yes** |
| `src/rainfall/dedupe.py` | Source Code | Vectorized duplicate resolution engine using Queen spatial neighbors and statistical median rules. | **Yes** |
| `src/rainfall/extremes.py` | Source Code | Anomaly detection module auditing rainfall readings $>500$ mm against neighboring districts. | **Yes** |
| `src/rainfall/hydrology_matrix.py` | Source Code | High-speed 2D NumPy calculation engine for rolling sums (3d/7d/30d), monsoon accumulations, and spell lengths. | **Yes** |
| `src/rainfall/classes.py` | Source Code | Official IMD categorical classification rules for rainfall intensity and departure percentages. | **Yes** |
| `src/rainfall/palette_lab.py` | Source Code | CIELAB perceptual uniformity checker and colorblindness simulator (Deuteranopia, Protanopia). | **Yes** |
| `src/rainfall/render_geom.py` | Source Code | Geometry data structures holding exploded polygon coordinates and bounding boxes. | **Yes** |
| `src/rainfall/render_geom_cache.py` | Source Code | Geometry caching system that saves exploded polygons to `geometry.pkl` for fast worker loading. | **Yes** |
| `src/rainfall/render_daily.py` | Source Code | Complete Matplotlib cartographic renderer (main map, inset boxes, dynamic cards, legend). | **Yes** |
| `src/rainfall/render_engine.py` | Source Code | High-speed frozen map renderer with direct Pillow Zlib image compression. | **Yes** |
| `src/rainfall/render_pool.py` | Source Code | Multiprocessing worker pool coordinator managing RAM headroom (~0.59 GB/worker) and progress watchdog. | **Yes** |
| `src/rainfall/m3_clean.py` | Source Code | Master pipeline coordinator orchestrating deduplication, crosswalk joining, matrix calculations, and Parquet writing. | **Yes** |
| `src/rainfall/m3_finalize.py` | Source Code | Aggregation exporter generating state/national summaries, monthly totals, and auto-generated data dictionary. | **Yes** |
| `scripts/render/render_all_daily_maps.py` | Script | Production script rendering all 1,800 daily choropleth maps in parallel. | **Yes** |
| `scripts/verify/qa_all_maps.py` | Script | Automated quality assurance script validating image dimensions, non-empty files, and visual integrity. | **Yes** |
| `outputs/maps/daily_actual/manifest.csv` | Output Report | Inventory manifest detailing district coverage, rain statistics, and wettest district for every rendered day. | **Yes** |
| `outputs/reports/data_audit_full.md` | Output Report | Detailed Markdown report auditing raw data quality, column statistics, and portal target comparison. | **Yes** |
| `outputs/reports/data_dictionary.md` | Output Report | Comprehensive data dictionary defining all 98 columns in the enriched master dataset. | **Yes** |

---

## 1.3 Folder Philosophy: Why Separation Matters

The project follows a strict **functional separation of concerns**. To understand why files are organized this way, think of the project like a professional kitchen preparing meals:

* **`data/raw/` = Raw Ingredients:** The raw, untouched produce straight from the market. We never modify, edit, or overwrite raw files manually. If a raw file is corrupted, we write code to clean it during ingestion, preserving the original source intact for auditable provenance.
* **`config/` = Recipe Settings & Cooking Parameters:** The spice measurements and oven temperatures. These files specify thresholds, file paths, and known spelling rules. Changing a setting in `config/config.yaml` modifies how the code executes without needing to rewrite Python logic.
* **`src/rainfall/` = Cooking Instructions & Chef Tools:** The reusable cooking techniques, recipes, and specialized knives. This library contains pure, testable Python functions and classes responsible for mathematical transformations, spatial matching, and image drawing.
* **`data/interim/` & `data/processed/` = Prepared & Cooked Ingredients:** Chopped vegetables and simmered sauces. These are intermediate and final datasets formatted for high-performance reading (Parquet) and matrix mathematics (NumPy).
* **`outputs/` = Plated Finished Dishes & Service Logs:** The final deliverables presented to the customer. This includes the 1,800 finished PNG maps, executive Markdown reports, statistical summary tables, and verification manifests.
* **`logs/` & `outputs/checkpoints/` = Kitchen Journal & Saved Progress:** The temperature logs and refrigerator checkpoints. They allow a long-running batch process (such as rendering 1,800 high-resolution maps) to safely resume from where it stopped if interrupted, without repeating hours of completed work.
* **`scripts/` = Automated Kitchen Appliances:** The automated blenders and dishwashers. These are lightweight command scripts that assemble the core library functions to execute batch workflows (such as rendering all maps or running QA audits).
* **`tests/` = Food Safety Inspection & Tripwires:** The safety checks that automatically catch mistakes before food leaves the kitchen. Automated tests guarantee that if a developer accidentally changes an algorithm or breaks a column calculation, the system alerts them immediately before generating incorrect maps.

<!-- SECTION 1 COMPLETE -->
