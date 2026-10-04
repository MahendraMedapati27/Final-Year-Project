# SECTION 7 — SCRIPTS AND AUTOMATED TESTS

---

## 7.1 Automated Scripts Ecosystem

The `scripts/` directory contains standalone executable automation tools divided into 4 functional areas:

```
scripts/
├── README.md                                   # Comprehensive script documentation and usage guide
├── run_python.ps1                              # PowerShell launcher for Windows Application Control environments
├── benchmarks/
│   └── timing_slice_render.py                  # Benchmarks multi-worker rendering throughput (frames/min)
├── pipeline/
│   └── resume_enrich.py                        # Safely resumes matrix feature enrichment after deduplication
├── render/
│   ├── build_geometry_cache.py                 # Pre-explodes GIS polygons into pickled PolyCollection cache
│   ├── render_all_daily_maps.py                # Master production script rendering all 1,800 daily choropleth maps
│   └── render_reference_trials.py              # Generates test frames for visual comparison
└── verify/
    ├── data_manifest_stats.py                  # Recomputes summary statistics for daily map manifests
    ├── data_matrix_check.py                    # Validates that render_matrix.npz matches rainfall_enriched.parquet
    ├── find_worst_layout_dates.py              # Identifies edge-case dates (widest legend, longest name, max rain)
    ├── map_full_qa.py                          # Comprehensive multi-point image and data integrity checker
    ├── map_parity_sample.py                    # Checks sample dates against approved reference PNGs
    ├── map_provenance.py                       # Validates data traceability from raw CSV -> parquet -> PNG pixel
    ├── maps_summary_and_contact_sheet.py       # Assembles high-resolution contact sheets for visual inspection
    ├── qa_all_maps.py                          # Production QA audit suite verifying all 1,800 rendered maps
    ├── qa_contact_sheet.py                     # Rapid contact sheet generator
    ├── qa_maps_light.py                        # Fast lightweight manifest and file existence validator
    ├── qa_reference_parity.py                  # Strict pixel-by-pixel parity test against reference gold standards
    └── rerender_stale_maps.py                  # Selectively re-renders only outdated or modified dates
```

---

## 7.2 Key Automation Scripts Explained

### 1. `scripts/render/build_geometry_cache.py`
* **Purpose:** Pre-processes the heavy `districts_master.gpkg` GIS file into Matplotlib `Path` and `PolyCollection` objects and saves them to `outputs/render_cache/<hash>/geometry.pkl`.
* **When Used:** Must be executed once before rendering maps, or whenever `config/config.yaml` map styling / boundary sources change.
* **Why it matters:** Eliminates the need for parallel worker processes to open and parse heavy GIS files, slashing worker startup time from 15 seconds to 0.4 seconds.

### 2. `scripts/render/render_all_daily_maps.py`
* **Purpose:** Master batch rendering script that coordinates the multi-process worker pool (`render_pool.py`) to render all 1,800 active observation dates.
* **Outputs:** 1,800 high-resolution PNG maps saved under `outputs/maps/daily_actual/YYYY/MM/rainfall_actual_YYYY-MM-DD.png` and the master manifest `manifest.csv`.
* **Execution:**
  ```powershell
  python scripts/render/render_all_daily_maps.py
  ```

### 3. `scripts/verify/qa_all_maps.py`
* **Purpose:** Exhaustive quality control audit that inspects all rendered PNG maps on disk.
* **What it verifies:**
  1. Exactly 1,800 PNG files exist in `outputs/maps/daily_actual/`.
  2. Zero 0-byte or corrupted image files.
  3. Every map has identical dimensions ($1500 \times 1650$ pixels).
  4. The error log `logs/render_errors.csv` is empty.
  5. `manifest.csv` contains complete statistical records for every date.

---

## 7.3 Automated Test Suite (`tests/`)

Automated tests act as **defensive tripwires**. If a developer accidentally alters a mathematical formula, breaks a file path, or introduces an overlap in the map layout, the test suite catches the bug immediately before bad maps are generated.

### Test Coverage Table

| Test File | What It Checks | Why It Matters | Bad Behavior Prevented |
| :--- | :--- | :--- | :--- |
| `tests/test_cli.py` | Typer CLI commands (`--help`, `ingest`, `audit`) | Ensures command-line subcommands execute without syntax crashes. | Broken terminal commands. |
| `tests/test_io.py` | Regex column mapping & PyArrow Parquet I/O | Verifies that all 25 raw columns map to clean snake_case names and save/load without data loss. | Dropped weather columns or corrupt timestamps. |
| `tests/test_geo.py` | GIS loading, valid geometry checks, and CRS projection | Confirms that `districts_master.gpkg` has 785 valid polygons and correctly projects to EPSG:4326. | Distorted map shapes or self-intersecting polygon errors. |
| `tests/test_p1b.py` | Duplicate reconciliation math | Tests that the 42,258 duplicate groups sum to exact expected accounting counts. | Accidental data deletion during deduplication. |
| `tests/test_m3_full.py` | End-to-end cleaning, deduplication, and hydrology matrix math | Proves that 3-day rolling sums strictly output `NaN` when a day is missing and dry/wet streaks calculate accurately. | False rain assumptions or inverted drought streaks. |
| `tests/test_render_p2.py` | Geometry cache creation and map rendering engine | Tests that `DailyMapRenderer` produces valid 1500x1650 PNG images with proper color palettes. | Corrupted image dimensions or blank map canvases. |
| `tests/test_frozen_layout_worst_case.py` | Bounding box text overlap on edge-case dates | Runs layout tests on extreme dates (longest district name, widest legend) to ensure text never overlaps map borders. | Illegible text collisions on final maps. |
| `tests/test_verify_stats.py` | Statistical aggregations and departure category formulas | Checks that national area-weighted rainfall and IMD departure bins match exact meteorological rules. | Incorrect rainfall classifications. |

---

## 7.4 Running the Test Suite

To run all automated tests across the entire codebase:

```powershell
pytest -v
```

All test modules run in seconds, confirming complete algorithmic and cartographic integrity.

<!-- SECTION 7 COMPLETE -->
