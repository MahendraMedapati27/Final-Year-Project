# SECTION 12 — END-TO-END DATA WALKTHROUGH

---

## 12.1 Tracing a Single Real Weather Observation

To understand how the entire system connects together, let us follow **ONE single real weather observation** through every stage of the pipeline:

> **The Observation:** Rainfall recorded in **Pune District, Maharashtra on August 15, 2023**.

```
[ Step 1: Raw CSV Row ]
      │
      ▼ (io.py: ingest_raw_csv)
[ Step 2: Interim Parquet Standardization ]
      │
      ▼ (audit.py: validation & coverage check)
[ Step 3: Statistical Audit & Recompute ]
      │
      ▼ (crosswalk.py & paint_groups.py)
[ Step 4: Geographic Name Matching to Polygon ID 412 ]
      │
      ▼ (dedupe.py: vectorized duplicate check)
[ Step 5: Cleaned & Deduped Observation ]
      │
      ▼ (hydrology_matrix.py: 2D NumPy Engine)
[ Step 6: 98-Column Enriched Analytical Record ]
      │
      ▼ (render.py: render_matrix.npz)
[ Step 7: Fast Render Matrix Array Lookup ]
      │
      ▼ (render_daily.py: DailyMapRenderer)
[ Step 8: Publication-Grade PNG Map ]
      │
      ▼ (qa_all_maps.py)
[ Step 9: Manifest Logging & QA Approval ]
```

---

## 12.2 Step-by-Step Data State Transformation

### Step 1: Raw CSV Ingestion
* **Location:** `data/raw/dataset_full.csv`
* **Raw Row Text:**
  `"India","Maharashtra","Pune","2023","15-08-2023",412.0,"Normal",...,"24.5","8.2","198.78",...`
* **What Happens:** `io.py:map_raw_columns()` parses the line, renames headers to snake_case, downcasts strings to categorical integers, and converts `"15-08-2023"` into a timestamp `date = 2023-08-15`.

### Step 2: Interim Parquet Storage
* **Location:** `data/interim/raw_full.parquet`
* **Stored State:**
  * `state` = `"Maharashtra"` (`category`)
  * `district` = `"Pune"` (`category`)
  * `date` = `2023-08-15` (`datetime64[ms]`)
  * `daily_actual_mm` = `24.5` (`float32`)
  * `daily_normal_mm` = `8.2` (`float32`)
  * `obj_id` = `412.0` (`float64`)

### Step 3: Statistical Audit & Validation
* **Module:** `src/rainfall/audit.py`
* **What Happens:** Verifies that $24.5$ mm falls within reasonable physical bounds ($0 \le x \le 1225$ mm).
* **Guarded Departure Recomputed:**
  $$\text{Departure \%} = \frac{24.5 - 8.2}{8.2} \times 100 = +198.78\%$$
* Recomputed value matches `daily_departure_pct_provided` exactly (agreement confirmed).

### Step 4: Geographic Matching & Crosswalk
* **Module:** `src/rainfall/crosswalk.py` & `names.py`
* **Normalized Key:** `"MAHARASHTRA::PUNE"`
* **Matching Algorithm:** Pass 1 Exact Match against `districts_master.gpkg`.
* **Matched Result:**
  * `shp_id` = `412`
  * `paint_group_uid` = `412`
  * `resolution` = `"direct"`
  * `match_score` = `100.0`
  * `area_km2` = `15,643.2`

### Step 5: Deduplication & QC Check
* **Module:** `src/rainfall/dedupe.py`
* **What Happens:** Checks whether another gauge report exists for Pune on `2023-08-15`. Since only one valid report exists, it flags `qc_dup_resolved = False`, `qc_negative_fixed = False`, and sets `daily_actual_mm_map = 24.5`.

### Step 6: Hydrology Matrix Calculations
* **Module:** `src/rainfall/hydrology_matrix.py`
* **Matrix Operations:**
  * Slices the dense NumPy array at Pune's paint group index (`pi=412`) and the date index for Aug 15 (`di=956`).
  * **3-Day Rolling Sum:** Sum of rainfall on Aug 13 ($5.0$ mm), Aug 14 ($10.5$ mm), and Aug 15 ($24.5$ mm):
    $$\text{rain\_3d\_mm} = 5.0 + 10.5 + 24.5 = 40.0\text{ mm}$$
  * **Intensity Classification:** $24.5$ mm falls in the $15.6 - 64.4$ mm range $\rightarrow$ Class `3` (**"Moderate Rain"**).
  * **Spells:** Since $24.5 \ge 2.5$ mm, `is_rainy_day = True`, `wet_spell_len` increments to `4`, and `dry_spell_len = 0`.
  * **Volumetric Water:**
    $$\text{daily\_volume\_mcm} = 24.5 \times 15643.2 \times 0.001 = 383.26\text{ Million } \text{m}^3$$
* **Master Parquet Output:** All 98 attributes merged into `data/processed/rainfall_enriched.parquet`.

### Step 7: Render Matrix Lookup
* **Location:** `data/processed/render_matrix.npz`
* **Stored Cell Value:** Row 956 (`2023-08-15`), Column 412 (`shp_id 412`) stores float value `24.5` and categorical class index `3`.

### Step 8: Cartographic Map Rendering
* **Module:** `src/rainfall/render_daily.py:DailyMapRenderer`
* **What Happens:**
  1. Worker loads pre-exploded Matplotlib `Path` for polygon 412 from `geometry.pkl`.
  2. Maps class `3` to Royal Blue hex color `#3878A8`.
  3. Updates Pune polygon facecolor to `#3878A8`.
  4. Incorporates Pune's rainfall into the dynamic national summary card statistics.
  5. Saves the final image to `outputs/maps/daily_actual/2023/08/rainfall_actual_2023-08-15.png`.

### Step 9: Manifest Logging & QA Verification
* **Module:** `scripts/verify/qa_all_maps.py`
* **What Happens:** Appends the record to `manifest.csv`, confirming non-zero file size, 1500x1650 pixel dimensions, and 100% pixel parity with reference layouts.

<!-- SECTION 12 COMPLETE -->
