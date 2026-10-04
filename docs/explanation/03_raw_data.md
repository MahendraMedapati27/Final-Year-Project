# SECTION 3 — RAW AND INTERIM DATA

---

## 3.1 Raw Data Provenance & Ingestion Strategy

The raw meteorological data in this project originates from the **National Data and Analytics Platform (NDAP)**, mirroring official observational records collected by the **India Meteorological Department (IMD)**.

The data is stored in the repository under `data/raw/`:
* `data/raw/dataset_full.csv`: The complete, untouched weather table (213.37 MB on disk, containing **1,320,770 rows** and 25 raw columns).
* `data/raw/dataset_sample_5k.csv`: A 5,000-row representative slice (1.09 MB) used for rapid unit testing, developer debugging, and continuous integration.

### Why Raw Files Must NEVER Be Edited Manually
In professional data engineering and scientific research, raw files are treated as **read-only historical artifacts**. If a human opens `dataset_full.csv` in Microsoft Excel or a text editor and modifies a typo:
1. The original source provenance is permanently destroyed.
2. Excel may silently alter dates, drop leading zeroes from administrative codes, or truncate long strings.
3. The pipeline would become non-reproducible: another researcher running the code on a fresh download from NDAP would get different results.

Instead, every cleaning step, name normalization, and anomaly fix is implemented **programmatically in Python code**, with complete audit logs and justification checkpoints recorded on disk.

---

## 3.2 Raw Schema & Column Mapping

The raw CSV file uses complex, human-formatted column titles that are inconvenient for computational pipelines (containing spaces, mixed capitalization, and historical typos like `"Monthly Acutual"`).

During Stage 1 ingestion (`src/rainfall/io.py`), the function `map_raw_columns()` uses regular expressions to match and rename all 25 raw columns to standardized, clean Python identifiers, and appends a parsed `date` column (resulting in a 26-column standardized table).

### Master Raw Column Schema Table

| Raw Column Header in CSV | Standardized Name | Ingested Data Type | Example Value | Description & Meaning | Used Downstream By |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `Country` | `country` | `category` | `"India"` | Country name (constant across all rows). | Metadata tracking |
| `State` | `state` | `category` | `"Maharashtra"` | State or Union Territory name. | `names.py`, `crosswalk.py`, `aggregates.py` |
| `District` | `district` | `category` | `"Pune"` | District name as reported by the weather gauge. | `names.py`, `crosswalk.py`, `dedupe.py` |
| `Year` | `year_label` | `category` | `"2023"` | Calendar year as a string label. | `audit.py`, `features.py` |
| `Calendar Day` | `calendar_day_raw` | `object` (string) | `"15-08-2023"` | Raw date string from gauge station. | Parsed into `date` by `io.py` |
| `Obj_Id` | `obj_id` | `float64` | `412.0` | Historical IMD numeric gauge/district station identifier. | `validate_crosswalk.py`, `dedupe.py` |
| `Daily Rainfall Category` | `daily_category_provided` | `category` | `"Excess"` | Meteorological intensity category provided in raw source. | `audit.py`, `classes.py` (agreement audit) |
| `Weekly Date` | `weekly_date_raw` | `category` | `"11-08-2023 to 17-08-2023"` | Multi-day weekly aggregation window label. | `features.py` (parsed into week bounds) |
| `Weekly Rainfall Category` | `weekly_category_provided` | `category` | `"Normal"` | Weekly departure category provided in source. | `audit.py` |
| `Cumulative Date` | `cumulative_date_raw` | `category` | `"01-06-2023 to 15-08-2023"` | Seasonal cumulative accumulation window label. | `features.py` (parsed into monsoon start) |
| `Cumulative Rainfall Category` | `cumulative_category_provided` | `category` | `"Excess"` | Cumulative departure category provided in source. | `audit.py` |
| `Monthly Date` | `monthly_date_raw` | `category` | `"01-08-2023 to 31-08-2023"` | Monthly calendar window label. | `features.py` |
| `Monthly Rainfall Category` | `monthly_category_provided` | `category` | `"Normal"` | Monthly departure category provided in source. | `audit.py` |
| `Daily Actual (in mm)` | `daily_actual_mm` | `float32` | `24.5` | **Core Variable:** Measured actual rainfall in millimeters for the day. | `dedupe.py`, `hydrology_matrix.py`, `render_daily.py` |
| `Daily Normal (in mm)` | `daily_normal_mm` | `float32` | `8.2` | Long-term historical baseline average rainfall for this district on this calendar day. | `audit.py`, `classes.py` (departure calculations) |
| `Daily Departure (in %)` | `daily_departure_pct_provided` | `float32` | `198.78` | Pre-calculated percentage departure provided by portal: $\frac{\text{Actual} - \text{Normal}}{\text{Normal}} \times 100$. | `audit.py` (agreement validation) |
| `Weekly Actual (in mm)` | `weekly_actual_mm_provided` | `float64` | `112.4` | Aggregated weekly actual rainfall provided by portal. | `audit.py`, `aggregates.py` |
| `Weekly Normal (in mm)` | `weekly_normal_mm_provided` | `float64` | `65.0` | Weekly historical baseline normal rainfall. | `audit.py` |
| `Weekly Departure (in %)` | `weekly_departure_pct_provided` | `float32` | `72.92` | Weekly percentage departure provided by portal. | `audit.py` |
| `Cumulative Actual (in mm)` | `cumulative_actual_mm_provided` | `float64` | `685.2` | Seasonal cumulative rainfall from monsoon onset. | `audit.py`, `hydrology_matrix.py` |
| `Cumulative Normal (in mm)` | `cumulative_normal_mm_provided` | `float64` | `540.0` | Cumulative historical baseline normal rainfall. | `audit.py` |
| `Cumulative Departure (in %)` | `cumulative_departure_pct_provided` | `float32` | `26.88` | Cumulative percentage departure provided by portal. | `audit.py` |
| `Monthly Actual (in mm)` | `monthly_actual_mm_provided` | `float64` | `310.5` | Monthly actual rainfall provided by portal. | `audit.py`, `aggregates.py` |
| `Monthly Normal (in mm)` | `monthly_normal_mm_provided` | `float64` | `280.0` | Monthly historical baseline normal rainfall. | `audit.py` |
| `Monthly Departure (in %)` | `monthly_departure_pct_provided` | `float32` | `10.89` | Monthly percentage departure provided by portal. | `audit.py` |
| *(Derived on Ingest)* | `date` | `datetime64[ms]` | `2023-08-15` | Clean, standardized timestamp parsed from `calendar_day_raw`. | Primary time-series index for all models |

---

## 3.3 Interim Parquet Optimization

During Stage 1 (`src/rainfall/io.py:ingest_raw_csv()`), the raw CSV is converted into an Apache Parquet binary file: `data/interim/raw_full.parquet`.

### Why Parquet Beats Raw CSV

1. **Massive Disk & RAM Reduction:**
   * Raw CSV on disk: **213.37 MB**
   * Compressed Parquet on disk: **12.29 MB** (a **94.2% reduction in size** using PyArrow Snappy compression).
2. **Lightning-Fast Read Speed:**
   * Reading `dataset_full.csv` with pandas takes ~15–25 seconds.
   * Reading `raw_full.parquet` takes **under 0.8 seconds**.
3. **Type Preservation:**
   * In a CSV, everything is text. Every time a script opens a CSV, it must guess whether `"2023-08-15"` is a date or string, and parse millions of numeric strings into floats.
   * Parquet stores binary types natively. Text columns are stored as compact integer dictionaries (`category`), numeric fields are stored as 32-bit floats (`float32`), and dates are stored as nanosecond timestamps (`datetime64[ms]`).
4. **Column Pruning (Predicate Pushdown):**
   * If a rendering script only needs `district`, `date`, and `daily_actual_mm`, Parquet allows the computer to read only those 3 columns from disk without loading the other 23 columns into memory.

---

## 3.4 Raw Data Imperfections & Audit Findings

During Stage 2 auditing (`src/rainfall/audit.py`), the system discovered several notable real-world data imperfections documented in `outputs/reports/data_audit_full.md` and `ASSUMPTIONS.md`:

### 1. Row Count Discrepancy
* **Observation:** The raw CSV contains **1,320,770 rows**. Preliminary NDAP documentation initially suggested ~1.05 million rows.
* **Audit Finding:** The dataset is broader than originally documented. Removing duplicate-key rows (46,586 rows) still leaves **1,274,184 clean records**. Value statistics (mean, min, max) match the government portal exactly, confirming that `dataset_full.csv` is the genuine, complete dataset.

### 2. Calendar Timeline & Missing Dates
* **Observation:** The dataset spans **2,088 total calendar days** between `2021-01-01` and `2026-09-19`.
* **Finding:** Weather observations are present for exactly **1,800 active dates**. There are **288 missing calendar gap days** where no weather stations reported data. The pipeline tracks these missing dates explicitly in `outputs/tables/missing_days_by_month.csv` and renders them with gray diagonal hatching on maps.

### 3. Raw Duplicate Keys
* **Observation:** The raw data contains **42,258 duplicate groups** where the exact same district and date combination appears two or more times (representing 88,844 total rows).
* **Cause:** Multiple regional weather reporting portals submitted overlapping daily summaries for the same administrative district. Stage 4 (`dedupe.py`) resolves every single duplicate group deterministically.

### 4. Extreme Values & Negative Readings
* **Observation:** A small number of records contained negative numbers (e.g., `-999.0` used by legacy sensors to indicate missing data) or values exceeding $500$ mm in a single day.
* **Handling:** Negative values are clamped to `NaN` and flagged under `qc_negative_fixed`. Extreme values $>500$ mm are audited against Queen spatial neighbors (`extremes.py`) to isolate gauge malfunctions (such as Jorhat on 2022-07-26) from genuine extreme monsoon storms.

<!-- SECTION 3 COMPLETE -->
