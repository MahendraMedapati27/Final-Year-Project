# SECTION 14 — COMPLETE ALPHABETIZED GLOSSARY

---

| Term | Simple Beginner Definition | Where It Matters in This Project |
| :--- | :--- | :--- |
| **Alias** | An alternate spelling, historical title, or phonetically different name for the same geographic region. | Defined in `config/name_aliases.csv` to map names like `"Baleshwar"` to `"Balasore"`. |
| **Bipartite Matching** | A graph theory problem of pairing elements from two distinct sets (e.g. dataset district names $\leftrightarrow$ map polygon names). | Solved globally using the Hungarian algorithm in `crosswalk.py`. |
| **Cache** | Pre-computed data saved in memory or on disk for instant retrieval rather than recalculating from scratch. | Pre-exploded polygons are saved in `outputs/render_cache/<hash>/geometry.pkl` for fast rendering. |
| **Checkpoint** | A saved snapshot of intermediate pipeline state that allows a process to resume without starting over. | Sliced annual checkpoints (`enriched_YYYY.parquet`) allow resuming feature enrichment. |
| **Choropleth Map** | A thematic map where geographic regions are shaded or colored according to a statistical variable. | The 1,800 daily rainfall maps generated in `outputs/maps/daily_actual/`. |
| **CIELAB** | A color space designed to be perceptually uniform to the human eye. | Used by `palette_lab.py` to ensure rainfall color bins have equal perceptual visual steps. |
| **CRS (Coordinate Reference System)** | Mathematical framework translating 3D Earth coordinates into a 2D map projection. | `EPSG:4326` (GPS degrees) used for mapping; `EPSG:7755` used for area calculations ($km^2$). |
| **Crosswalk** | A lookup translation table that connects entity names or identifiers across disparate datasets. | `data/processed/district_crosswalk.csv` connects weather rows to map polygons. |
| **CSV (Comma-Separated Values)** | A plain-text tabular file format where lines represent rows and commas separate column values. | Raw input data format (`data/raw/dataset_full.csv`). |
| **Deduplication** | The process of resolving multiple conflicting reports for the exact same entity and timestamp. | `dedupe.py` resolves 42,258 duplicate district-date groups. |
| **Departure** | The percentage deviation of measured rainfall from long-term historical normal baseline. | Computed as $(\text{Actual} - \text{Normal}) / \text{Normal} \times 100$, guarded by 2.5 mm threshold. |
| **DPI (Dots Per Inch)** | A measure of spatial image resolution; higher DPI yields sharper maps. | Configured to 150 DPI in `config.yaml` to generate crisp $1500 \times 1650$ pixel maps. |
| **Dry Spell** | A continuous run of consecutive days where daily rainfall remains below 2.5 mm. | Tracked as `dry_spell_len` in `hydrology_matrix.py` for agricultural drought monitoring. |
| **Fuzzy Matching** | Measuring textual similarity between two strings using Levenshtein distance formulas. | Used via RapidFuzz token matching ($\ge 92\%$) in `crosswalk.py`. |
| **GeoPackage (.gpkg)** | An open, non-proprietary SQLite-based container format for geographic vector data. | Used to store official district boundaries in `data/geo/districts_master.gpkg`. |
| **Hungarian Algorithm** | A combinatorial optimization algorithm that finds the globally optimal 1-to-1 matching in polynomial time. | Used in `crosswalk.py` to assign remaining district names to polygons without duplicates. |
| **IMD** | India Meteorological Department; the national meteorological agency of India. | Source of meteorological standards, intensity thresholds, and departure bins. |
| **Intersection-over-Union (IoU)** | A geometric ratio measuring the spatial overlap area between two geographic polygons. | Used in `validate_crosswalk.py` to verify polygon alignment. |
| **LGD** | Local Government Directory; the official administrative classification system of India. | Provides the 785 modern district boundaries used in `districts_master.gpkg`. |
| **Manifest** | An inventory table cataloging generated files alongside their metadata and summary metrics. | Generated as `outputs/maps/daily_actual/manifest.csv`. |
| **Million Cubic Meters (MCM)** | Volumetric unit of water ($1\text{ MCM} = 1,000,000\text{ m}^3$). | Computed as $\text{Rainfall (mm)} \times \text{Area } (km^2) \times 0.001$ in `schema.py`. |
| **Monsoon Cumulative** | Total accumulated rainfall since June 1st of each calendar year. | Tracked as `monsoon_cum_mm` in `hydrology_matrix.py`. |
| **NaN (Not a Number)** | A numerical representation in computing indicating missing, undefined, or null data. | Used when rain data is unobserved or baseline normal is below guard thresholds. |
| **NDAP** | National Data and Analytics Platform (NITI Aayog, Government of India). | The data portal from which the raw weather dataset was acquired. |
| **Paint Group** | A logical grouping identifier that links map polygons to weather data records. | Resolves parent-child split districts in `paint_groups.py`. |
| **Parquet (Apache Parquet)** | A columnar binary storage format optimized for high-speed analytical queries and compression. | Used for interim and processed datasets (`raw_full.parquet`, `rainfall_enriched.parquet`). |
| **PolyCollection** | A Matplotlib graphics container that draws hundreds of polygon paths in a single draw call. | Used in `DailyMapRenderer` to achieve 0.35 s/map render speed. |
| **Polygon** | A closed 2D geographic shape representing an administrative district boundary. | Stored in `districts_master.gpkg`. |
| **Predicate Pushdown** | An optimization in columnar databases allowing readers to load specific columns without parsing the whole file. | Enabled by Apache Parquet and PyArrow. |
| **QA (Quality Assurance)** | Automated verification processes proving outputs are mathematically and visually accurate. | Implemented in `scripts/verify/qa_all_maps.py`. |
| **Queen Neighbors** | Spatial adjacency where polygons sharing either an edge or a vertex are classified as neighbors. | Used in `dedupe.py` and `extremes.py` via Libpysal. |
| **Rolling Window** | A moving statistical calculation over a fixed window of consecutive days (e.g. 3, 7, 30 days). | Calculated using strict 2D NumPy slices in `hydrology_matrix.py`. |
| **Survey of India (SOI)** | The national mapping agency of India. | Source of the official national outer boundary in `india-soi.geojson`. |
| **Vector Data** | Spatial data represented as mathematical coordinates and geometric shapes (points, lines, polygons). | Stored in GeoPackage and GeoJSON files. |
| **Wet Spell** | A continuous run of consecutive days where daily rainfall is $\ge 2.5$ mm. | Tracked as `wet_spell_len` in `hydrology_matrix.py`. |
| **Worker Process** | An independent parallel Python process running on a dedicated CPU core. | Coordinated via `render_pool.py` for parallel map generation. |

<!-- SECTION 14 COMPLETE -->
