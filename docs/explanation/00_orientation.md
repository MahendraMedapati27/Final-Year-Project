# SECTION 0 — PROJECT ORIENTATION

---

## 0.1 What is this project?

This project is an **end-to-end data processing, quality assurance, hydrological modeling, and automated cartography (map generation) system** for Indian meteorological data. It takes real-world daily rainfall records covering **700+ Indian districts across nearly six years (January 1, 2021 to September 19, 2026)** sourced from the National Data and Analytics Platform (NDAP) / India Meteorological Department (IMD) and transforms them into verified analytical datasets and publication-quality daily choropleth maps.

The project exists because raw government weather datasets are notoriously messy: they contain naming inconsistencies, duplicate records with conflicting numbers, missing calendar dates, sensor anomalies, and historical administrative district reorganizations (districts splitting or merging over time). Furthermore, generating thousands of high-resolution, cartographically accurate daily maps manually would take months of human effort. This system automates the entire ingestion, cleaning, geographic reconciliation, hydrological modeling (calculating 3-day/7-day/30-day rolling sums, monsoon cumulative totals, and dry/wet spells), and parallel map rendering pipeline—producing **1,800 publication-grade PNG daily maps** with frozen layout parity and zero human intervention.

The final outputs serve hydrologists, disaster management authorities, agricultural planners, and policy researchers who need clear, auditable spatial intelligence about drought progression, flood risks, and monsoon dynamics across India.

---

## 0.2 The Complete Pipeline

The project operates as an automated 7-stage sequential pipeline with strict quality gates at every transition:

```
[ Stage 1: Ingest ] ──> [ Stage 2: Audit ] ──> [ Stage 3: Geographic Crosswalk & Paint Groups ]
                                                                     │
[ Stage 6: Render ] <── [ Stage 5: Hydrology Matrix ] <── [ Stage 4: Cleaning & Deduplication ]
        │
        └──> [ Stage 7: Quality Assurance & Manifest Verification ]
```

### Stage 1: Ingest
* **What enters:** Raw CSV files (`data/raw/dataset_full.csv` ~213 MB, 1,320,770 rows, or `dataset_sample_5k.csv`).
* **What happens:** The system reads the header line, matches messy or misspelled column names (such as `"Monthly Acutual"`) using regular expressions, standardizes column names, optimizes data types (converting text strings to categorical types, dates to `datetime64[ms]`, and numeric rainfall values to `float32`), and compresses the data into Apache Parquet format using the `pyarrow` engine.
* **What leaves:** Standardized interim columnar files: `data/interim/raw_full.parquet` (12.3 MB) or `data/interim/raw_sample.parquet` (0.14 MB).

### Stage 2: Audit
* **What enters:** `data/interim/raw_full.parquet` and threshold expectations defined in `config/config.yaml`.
* **What happens:** The system profiles column value ranges (min, max, mean, median, null counts), verifies calendar continuity (discovering 1,800 active observation dates and 288 missing calendar gap days), checks raw duplicate keys, and recomputes percentage departures from normal rainfall to test portal agreement.
* **What leaves:** Comprehensive markdown audit reports (`outputs/reports/data_audit_full.md`), duplicate key logs, and category cross-tabulation tables.

### Stage 3: Geographic Crosswalk & Paint Groups
* **What enters:** Modern 2026 Local Government Directory (LGD) district boundaries (`data/geo/districts_master.gpkg`, 785 polygons), Survey of India (SOI) external boundary outline (`data/geo/candidates/india-soi.geojson`), historical name alias lookup (`config/name_aliases.csv`), manual boundary overrides (`config/manual_overrides.csv`), and the unique state/district combinations from the weather dataset.
* **What happens:** The system executes a multi-pass hierarchical matching engine:
  1. *Pass 0:* Manual overrides for known boundary swaps (e.g., Bengaluru Urban vs. Rural).
  2. *Pass 1 & 2:* Exact and case/punctuation-normalized string matching.
  3. *Pass 3:* Token-based fuzzy string matching (RapidFuzz threshold $\ge 92\%$).
  4. *Pass 4:* Global bipartite matching using the Hungarian optimization algorithm (`scipy.optimize.linear_sum_assignment`).
  5. *Paint Group Resolution:* Newly carved modern districts present in the 785-polygon map but missing from historical weather reports are resolved via spatial geometric intersection—identifying which parent IMD boundary contains $\ge 50\%$ of the child polygon and inheriting parent data under a `child_of_<Parent>` tag.
* **What leaves:** `data/processed/district_crosswalk.csv` and `data/processed/paint_group_polygons.csv` mapping all 785 map polygons into 783 paint groups (731 direct, 28 child orphans, 24 unassignable `no_data` polygons).

### Stage 4: Cleaning & Deduplication
* **What enters:** `data/interim/raw_full.parquet` + Crosswalk tables.
* **What happens:** The cleaning engine resolves 42,258 duplicate district-date groups (same district reported multiple times on the same date):
  * Retains non-null actual rainfall values over nulls.
  * Averages close values (difference $< 0.5$ mm).
  * Uses Queen spatial neighbors (checking surrounding districts) to pick the most plausible reading when conflicting values exist.
  * Marks irreconcilable wild conflicts as `NaN` with a QC flag (`qc_dup_unresolvable`).
  * Clamps negative rainfall to `NaN` (`qc_negative_fixed`) and flags spatial outlier extremes ($>500$ mm, e.g., Jorhat on 2022-07-26).
* **What leaves:** `data/processed/checkpoints/deduped.parquet` (exactly 1,274,184 clean rows; 46,586 duplicate rows eliminated).

### Stage 5: Hydrology Matrix Calculations & Feature Enrichment
* **What enters:** Deduplicated daily rainfall records indexed across 783 paint groups and 2,088 continuous calendar days.
* **What happens:** Instead of slow row-by-row pandas grouping, the system pivots the data into a dense 2D NumPy array $[783 \times 2088]$. In seconds, vectorized array math calculates:
  * Strict 3-day, 7-day, and 30-day cumulative rolling sums (preserving `NaN` on missing observations).
  * Monsoon cumulative totals resetting every June 1st.
  * Continuous dry spell streaks ($<2.5$ mm) and wet spell streaks ($\ge 2.5$ mm).
  * Days since last rain.
  * Standard IMD rainfall intensity bins and departure categories.
* **What leaves:** The master analytical dataset `data/processed/rainfall_enriched.parquet` (98 schema columns, 1,274,184 rows) and the compact map rendering matrix `data/processed/render_matrix.npz` (1,800 active dates $\times$ 783 polygons).

### Stage 6: Automated Map Rendering
* **What enters:** `render_matrix.npz` and pre-exploded geometry cache (`outputs/render_cache/<hash>/geometry.pkl`).
* **What happens:** High-speed parallel rendering pool (`render_pool.py`) loads polygon geometries once as Matplotlib `PolyCollection` paths. Worker processes (scaled to available RAM at ~0.59 GB/worker) update the color array for each date, apply official IMD color bins (from "No Rain" `#EFEFEF` to "Extremely Heavy" `#081820` / categorical ramps), render Andaman/Nicobar and Lakshadweep inset boxes, draw dynamic statistical cards and legends, and save compressed PNG images using Pillow.
* **What leaves:** 1,800 high-resolution daily PNG maps stored in `outputs/maps/daily_actual/YYYY/MM/rainfall_actual_YYYY-MM-DD.png` (1500 $\times$ 1650 pixels @ 150 DPI).

### Stage 7: Quality Assurance & Manifest Verification
* **What enters:** Rendered PNG maps, `manifest.csv`, and reference parity targets (`approved_2021-01-31.png`, `approved_2026-09-19.png`).
* **What happens:** Automated QA suites verify:
  * 100% pixel parity ($0\%$ pixel difference $>24$ intensity vs. approved layout).
  * Non-zero file sizes and identical dimensions.
  * Provenance traceability (linking every pixel back to the source Parquet row).
  * Absence of dynamic text collisions/overlaps.
* **What leaves:** `outputs/maps/daily_actual/manifest.csv`, `outputs/checkpoints/p5_qa.json`, and contact sheets for visual inspection.

---

## 0.3 Pipeline Diagram

```text
+-------------------------------------------------------------+
|                      RAW DATA LAYER                         |
|  data/raw/dataset_full.csv (~213 MB, 1.32M rows, 25 cols)  |
+-------------------------------------------------------------+
                              |
                              | [io.py: ingest_raw_csv()]
                              v
+-------------------------------------------------------------+
|                     INTERIM PARQUET                         |
|  data/interim/raw_full.parquet (12.3 MB, 1.32M rows)        |
+-------------------------------------------------------------+
                              |
                              +-------------------------------+
                              |                               |
                              | [audit.py]                    | [crosswalk.py & geo.py]
                              v                               v
+------------------------------------+  +------------------------------------+
|            AUDIT REPORTS           |  |       GEOMETRY & CROSSWALK         |
| outputs/reports/data_audit_full.md |  | data/geo/districts_master.gpkg     |
| outputs/tables/duplicates_analysis |  | config/name_aliases.csv            |
+------------------------------------+  | config/manual_overrides.csv        |
                                        +------------------------------------+
                                                      |
                                                      | [paint_groups.py]
                                                      v
                                        +------------------------------------+
                                        |   data/processed/                  |
                                        |   - district_crosswalk.csv         |
                                        |   - paint_group_polygons.csv       |
                                        +------------------------------------+
                                                      |
                              +-----------------------+
                              |
                              | [dedupe.py, m3_clean.py: vectorized_dedupe()]
                              v
+-------------------------------------------------------------+
|                   CLEANED & DEDUPED DATA                    |
|  data/processed/checkpoints/deduped.parquet (1.27M rows)    |
|  42,258 duplicate groups resolved (46,586 duplicate rows)  |
+-------------------------------------------------------------+
                              |
                              | [hydrology_matrix.py: build_paint_group_matrix()]
                              v
+-------------------------------------------------------------+
|               HYDROLOGY MATRIX ENGINE (NUMPY)               |
|  Dense Matrix: 783 Paint Groups x 2088 Continuous Days      |
|  - 3d, 7d, 30d Rolling Rain Sums (strict NaN handling)      |
|  - Monsoon Cumulative Sums (reset June 1)                   |
|  - Dry Spells (<2.5mm) & Wet Spells (>=2.5mm)               |
+-------------------------------------------------------------+
                              |
                              +-------------------------------+
                              |                               |
                              v                               v
+------------------------------------+  +------------------------------------+
|     ENRICHED MASTER DATASET        |  |        MAP RENDER MATRIX           |
| data/processed/                    |  | data/processed/render_matrix.npz   |
|   rainfall_enriched.parquet        |  | (1800 active dates x 783 polygons) |
| (1,274,184 rows, 98 columns)       |  +------------------------------------+
+------------------------------------+                |
                                                      | [build_geometry_cache.py]
                                                      v
                                        +------------------------------------+
                                        |       FROZEN GEOMETRY CACHE        |
                                        | outputs/render_cache/<hash>/       |
                                        |   geometry.pkl (PolyCollections)   |
                                        +------------------------------------+
                                                      |
                                                      | [render_pool.py & render_daily.py]
                                                      v
+-------------------------------------------------------------+
|                 PARALLEL MAP RENDER ENGINE                  |
|  - Multi-process worker pool (RAM-aware: ~0.59 GB/worker)   |
|  - Matplotlib PolyCollection + Pillow Direct Compression    |
|  - Inset maps (A&N, Lakshadweep), Legends, Stat Cards       |
+-------------------------------------------------------------+
                              |
                              +-------------------------------+
                              |                               |
                              v                               v
+------------------------------------+  +------------------------------------+
|         FINAL DAILY MAPS           |  |        QA & VERIFICATION           |
| outputs/maps/daily_actual/         |  | outputs/maps/daily_actual/         |
|   YYYY/MM/rainfall_actual_*.png    |  |   manifest.csv                     |
| (1,800 maps @ 1500x1650 px, 150dpi)|  | outputs/checkpoints/p5_qa.json     |
+------------------------------------+  +------------------------------------+
```

---

## 0.4 Running Glossary

To understand this project without confusion, here are the core technical terms defined simply:

* **Dataframe:** A digital tabular grid of data organized into rows and columns, similar to an Excel sheet, managed in Python using libraries like pandas or polars.
* **Row:** A single horizontal record representing an observation (for example, the rainfall recorded in Pune on August 15, 2023).
* **Column:** A vertical attribute describing a property of the data (such as `state`, `date`, `daily_actual_mm`, or `dry_spell_len`).
* **CSV (Comma-Separated Values):** A plain-text file format where table rows are written as lines of text and column values are separated by commas.
* **Parquet (Apache Parquet):** A modern, high-performance binary file format that stores data in columns rather than rows. It compresses file sizes by 80–90% and allows software to load only the specific columns needed in milliseconds.
* **Polygon:** In GIS (Geographic Information Systems), a closed 2D shape defined by a sequence of latitude and longitude coordinates that represents the spatial boundary of an administrative region (such as a district or state).
* **Shapefile / GeoPackage (.gpkg) / GeoJSON:** Digital file formats used to store geographic shapes (points, lines, polygons) along with their administrative attributes.
* **CRS (Coordinate Reference System):** A mathematical system that translates 3D locations on the curved Earth surface into 2D coordinates on a flat map (e.g., EPSG:4326 for standard GPS coordinates, EPSG:7755 for equal-area Indian projections).
* **Join / Merge:** Combining two separate tables into one by matching rows that share a common identifier (such as matching a weather table with a geographic polygon table using district names).
* **Deduplication:** The process of identifying and resolving multiple conflicting or redundant records for the exact same district and date so each district has exactly one valid reading per day.
* **Choropleth Map:** A thematic map where geographic regions (districts) are shaded or colored according to the value of a statistical variable (such as rainfall depth or departure).
* **DPI (Dots Per Inch):** A measure of spatial printing/display resolution. Higher DPI means sharper lines and clearer text (this project renders maps at 150 DPI).
* **Worker Process:** An independent instance of Python running in parallel on a CPU core to perform tasks (such as rendering map frames) simultaneously without blocking the main program.
* **Cache:** Pre-computed and saved data (such as complex polygon coordinates) stored in memory or on disk so it can be reused instantly instead of recalculating it from scratch every time.
* **Checkpoint:** A saved snapshot of data at a specific stage in the pipeline that allows the pipeline to safely resume from where it stopped if interrupted, without repeating hours of earlier processing.
* **Manifest:** An inventory table listing every generated output file along with its metadata, summary statistics, and verification flags.
* **QA (Quality Assurance):** Automated tests and validation checks that prove outputs are mathematically accurate, complete, and visually correct before publication.
* **NaN (Not a Number) / Null:** A placeholder in computing representing missing, unavailable, or corrupted data.
* **Rolling Window:** A moving calculation that computes a statistic (like the total rainfall sum) over a fixed window of consecutive days (e.g., the last 3, 7, or 30 days) ending on the current date.
* **Crosswalk:** A lookup translation table that connects names from one dataset to names or IDs in another dataset (e.g., matching historical weather names like `"Baleshwar"` to modern map polygon names like `"Balasore"`).
* **Alias:** An alternate spelling, naming variant, or historical name for the same geographic district.
* **Fuzzy Matching:** An algorithmic technique that measures the textual similarity between two strings (even if misspelled or abbreviated) using Levenshtein distance calculations.
* **Vector Data:** Geographic data represented as mathematical geometric points, lines, and polygons.
* **Raster Data:** Geographic or visual data represented as a regular grid of pixels or cells (such as a PNG image).
* **Hungarian Algorithm:** A combinatorial optimization algorithm that solves the bipartite assignment problem in polynomial time, guaranteeing the best possible global pairing of dataset names to map polygons without duplicate assignments.
* **Paint Group:** A logical grouping identifier that links map polygons to weather data records, allowing child districts formed after historical weather datasets began to inherit the weather values of their parent district.

<!-- SECTION 0 COMPLETE -->
