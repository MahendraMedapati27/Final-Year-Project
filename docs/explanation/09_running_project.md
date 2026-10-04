# SECTION 9 — HOW TO RUN THE PROJECT AND RECOVER FROM FAILURES

---

## 9.1 Step-by-Step Execution Guide

Below are the exact, verified commands required to run the entire project from scratch:

```powershell
# -------------------------------------------------------------
# STEP 0: Environment Setup
# -------------------------------------------------------------
cd "D:\final year project"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .

# -------------------------------------------------------------
# STEP 1: Ingest Raw CSV to Standardized Parquet
# -------------------------------------------------------------
# Ingests data/raw/dataset_full.csv -> data/interim/raw_full.parquet (12.3 MB)
python -m rainfall.cli ingest

# -------------------------------------------------------------
# STEP 2: Audit Dataset & Check Portal Target Reconciliation
# -------------------------------------------------------------
# Generates outputs/reports/data_audit_full.md and missing date tables
python -m rainfall.cli audit

# -------------------------------------------------------------
# STEP 3: Geographic Boundary Matching & Crosswalk Generation
# -------------------------------------------------------------
# Generates data/processed/district_crosswalk.csv and paint_group_polygons.csv
python -m rainfall.cli paint-groups

# -------------------------------------------------------------
# STEP 4: Run Deduplication, Cleaning & Hydrology Matrix Enrichment
# -------------------------------------------------------------
# Resolves 42,258 duplicate groups, computes rolling sums, and writes master parquet
python -m rainfall.cli clean --all --fresh

# -------------------------------------------------------------
# STEP 5: Verify Schema & Row Accounting Integrity Gate
# -------------------------------------------------------------
# Confirms exactly 1,274,184 rows and 98 columns are present
python -m rainfall.cli verify

# -------------------------------------------------------------
# STEP 6: Pre-compute Exploded Polygon Geometry Cache
# -------------------------------------------------------------
# Builds outputs/render_cache/<hash>/geometry.pkl (PolyCollections)
python scripts/render/build_geometry_cache.py

# -------------------------------------------------------------
# STEP 7: Render All 1,800 High-Resolution Daily Maps in Parallel
# -------------------------------------------------------------
# Multiprocessing render: outputs/maps/daily_actual/YYYY/MM/*.png
python scripts/render/render_all_daily_maps.py

# -------------------------------------------------------------
# STEP 8: Quality Assurance & Manifest Verification
# -------------------------------------------------------------
# Audits all rendered PNG files and verifies manifest.csv
python scripts/verify/qa_all_maps.py
```

---

## 9.2 Pipeline Stage Execution Matrix

| Step | Command | Input Artifacts | Output Deliverables | Verified Execution Time |
| :--- | :--- | :--- | :--- | :--- |
| **1. Ingest** | `python -m rainfall.cli ingest` | `data/raw/dataset_full.csv` | `data/interim/raw_full.parquet` | ~4–8 seconds |
| **2. Audit** | `python -m rainfall.cli audit` | `data/interim/raw_full.parquet` | `outputs/reports/data_audit_full.md` | ~15–30 seconds |
| **3. Crosswalk** | `python -m rainfall.cli paint-groups` | `districts_master.gpkg`, aliases | `district_crosswalk.csv`, `paint_group_polygons.csv` | ~5–10 seconds |
| **4. Clean** | `python -m rainfall.cli clean --all --fresh` | `raw_full.parquet`, crosswalk | `rainfall_enriched.parquet` (98 cols), `render_matrix.npz` | ~45–90 seconds |
| **5. Verify** | `python -m rainfall.cli verify` | `rainfall_enriched.parquet` | `outputs/checkpoints/verify.json` | ~2–4 seconds |
| **6. Cache** | `python scripts/render/build_geometry_cache.py` | `districts_master.gpkg`, `config.yaml` | `outputs/render_cache/<hash>/geometry.pkl` | ~8–12 seconds |
| **7. Render** | `python scripts/render/render_all_daily_maps.py` | `render_matrix.npz`, `geometry.pkl` | 1,800 PNG maps + `manifest.csv` | ~12–25 minutes (multi-core) |
| **8. QA** | `python scripts/verify/qa_all_maps.py` | 1,800 PNG maps, `manifest.csv` | `outputs/checkpoints/p5_qa.json` | ~10–15 seconds |

---

## 9.3 Failure Recovery & Resumability Guide

Because the pipeline processes over 1.3 million rows and renders thousands of high-resolution images, failures could occur if the computer runs out of memory, is powered off, or experiences a thread crash. The system includes built-in **resumability mechanisms**:

### Scenario A: Rendering Was Interrupted Halfway
* **How It Works:** `render_pool.py` checks whether `rainfall_actual_YYYY-MM-DD.png` already exists on disk before rendering. If 1,000 maps are already complete and power fails, restarting `render_all_daily_maps.py` instantly skips the completed 1,000 maps and renders only the remaining 800 days.
* **To Force Re-render:** Add the `--overwrite` flag:
  ```powershell
  python scripts/render/render_all_daily_maps.py --overwrite
  ```

### Scenario B: Feature Enrichment Crashed Due to RAM OOM
* **What Happened:** In early development, writing large Parquet files with multi-threaded OpenBLAS on Windows caused an Out-of-Memory crash (`logs/clean_memory.jsonl` peak RSS ~1816 MB).
* **Built-in Fix:** `cli.py` automatically sets environment variables before importing NumPy:
  ```python
  os.environ["OMP_NUM_THREADS"] = "4"
  os.environ["OPENBLAS_NUM_THREADS"] = "4"
  ```
* **Recovery:** Sliced annual checkpoint files (`data/processed/checkpoints/enriched_YYYY.parquet`) are preserved. You can resume merging without restarting deduplication via:
  ```powershell
  python scripts/pipeline/resume_enrich.py
  ```

### Scenario C: Windows Application Control Blocks `.venv` DLLs
* **Symptom:** On certain institutional or university Windows machines, executing Python from `.venv\Scripts\python.exe` causes a DLL block on Pandas/PyArrow C-extensions.
* **Solution:** Use the provided PowerShell helper script, which executes through Anaconda base Python:
  ```powershell
  .\scripts\run_python.ps1 scripts\render\render_all_daily_maps.py
  ```

<!-- SECTION 9 COMPLETE -->
