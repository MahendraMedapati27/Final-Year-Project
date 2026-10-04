# SECTION 4 — CORE SOURCE CODE DEEP DIVE

---

## 4.1 Architecture of `src/rainfall/`

The `src/rainfall/` directory houses the entire computational engine of the project. It is structured into logical layers:

```
[ Configuration & Utilities ]  -->  config.py, names.py, memory_log.py, schema.py
[ Ingestion & Profiling ]      -->  io.py, audit.py, duplicates.py
[ GIS & Geographic Matching ]  -->  geo.py, crosswalk.py, paint_groups.py, validate_crosswalk.py
[ Data Cleaning & QC ]         -->  dedupe.py, extremes.py, m3_clean.py, p1b.py
[ Hydrological Modeling ]      -->  hydrology_matrix.py, classes.py, features.py, aggregates.py
[ High-Performance Rendering ] -->  render_geom.py, render_geom_cache.py, render_daily.py, render_engine.py, render_pool.py
[ Gates, QA & Verification ]   -->  gates.py, p1_gate.py, verify.py, verify_matrix.py, cli.py
```

Below is the exhaustive, file-by-file technical and conceptual breakdown for every meaningful module.

---

## 4.2 Module: `src/rainfall/config.py`

### 4.2.1 Purpose
Provides centralized, cross-platform path resolution and YAML configuration loading, ensuring file operations work seamlessly on Windows, Linux, or macOS.

### 4.2.2 Inputs & Outputs
* **Reads:** `config/config.yaml`
* **Produces:** In-memory configuration dictionary with absolute `pathlib.Path` objects.

### 4.2.3 Important Functions
* `project_root() -> Path`: Ascends parent directories until finding `pyproject.toml` or `config/config.yaml`.
* `load_config() -> dict[str, Any]`: Parses `config/config.yaml`.
* `resolve_path(rel_or_abs) -> Path`: Resolves relative paths relative to workspace root.

### 4.2.4 Real Code Snippet (`src/rainfall/config.py:13–36`)

```python
def project_root() -> Path:
    p = Path(__file__).resolve().parent
    for _ in range(5):
        if (p / "config" / "config.yaml").exists() or (p / "pyproject.toml").exists():
            return p
        p = p.parent
    return Path.cwd()


def load_config(path: Path | None = None) -> dict[str, Any]:
    p = path or (project_root() / "config" / "config.yaml")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_path(p: str | Path) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    return project_root() / path
```

### 4.2.5 Beginner Explanation & Viva Tip
> **In One Sentence:** `config.py` tells the rest of the project where files live on your computer and loads your project settings.
> **Professor Question:** *How does your code prevent broken file paths when moving between Windows and Linux machines?*
> **Student Answer:** We avoid hardcoded strings like `C:\` or `/home/` and use `pathlib.Path` inside `config.py` to dynamically locate the project root relative to `pyproject.toml`.

---

## 4.3 Module: `src/rainfall/io.py`

### 4.3.1 Purpose
Performs fast, robust CSV ingestion, regular expression column mapping, data type downcasting, Parquet serialization, and cryptographic SHA-256 manifest logging.

### 4.3.2 Inputs & Outputs
* **Reads:** `data/raw/dataset_full.csv` (or sample).
* **Produces:** `data/interim/raw_full.parquet` and `logs/ingest_full_manifest.json`.

### 4.3.3 Detailed Code Walkthrough (`src/rainfall/io.py:52–114`)

```python
def map_raw_columns(raw_names: list[str]) -> dict[str, str]:
    """Map raw CSV header names to snake_case logical names by position + regex."""
    if len(raw_names) != EXPECTED_N_COLS:
        raise ValueError(f"Expected {EXPECTED_N_COLS} columns, got {len(raw_names)}")
    mapping: dict[str, str] = {}
    used_targets: set[str] = set()
    for i, raw in enumerate(raw_names):
        matched = False
        for pattern, target in COLUMN_PATTERNS:
            if re.search(pattern, raw, re.IGNORECASE):
                if target in used_targets:
                    raise ValueError(f"Duplicate target {target} for column {raw!r}")
                mapping[raw] = target
                used_targets.add(target)
                matched = True
                break
        if not matched:
            raise ValueError(f"No pattern for column index {i}: {raw!r}")
    if len(mapping) != EXPECTED_N_COLS:
        raise ValueError(f"Mapped {len(mapping)} columns, expected {EXPECTED_N_COLS}")
    return mapping
```

**Line-by-Line Logic:**
1. Verifies that the CSV has exactly 25 columns.
2. Iterates over each column header in the raw file.
3. Compares the header against compiled regular expressions (such as `r"^Monthly Acutual|^Monthly Actual"`).
4. Prevents two raw columns from accidentally mapping to the same target name (`used_targets`).
5. Returns a rename dictionary mapping messy headers to clean snake_case identifiers.

### 4.3.4 Ingestion & Parquet Writing (`src/rainfall/io.py:80–120`)

```python
def ingest_raw_csv(csv_path: Path) -> pd.DataFrame:
    raw_cols = read_raw_header(csv_path)
    col_map = map_raw_columns(raw_cols)
    df = pd.read_csv(csv_path, engine="pyarrow")
    df = df.rename(columns=col_map)
    # Downcast strings to categories and numbers to float32
    for cat_col in ["country", "state", "district", "year_label", ...]:
        if cat_col in df.columns:
            df[cat_col] = df[cat_col].astype("category")
    df["date"] = pd.to_datetime(df["calendar_day_raw"], errors="coerce")
    for c in df.columns:
        if c.endswith("_mm") or c.endswith("_pct_provided"):
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
    return df
```

### 4.3.5 Beginner Explanation & Viva Tip
> **In One Sentence:** `io.py` safely ingests messy raw CSV tables, fixes header typos with regex, converts data types to save RAM, and writes fast Parquet files.
> **Professor Question:** *Why did you downcast numeric rainfall columns from 64-bit to 32-bit floats?*
> **Student Answer:** 32-bit floats provide up to 7 decimal digits of precision, which is more than sufficient for rainfall measured to 0.1 mm, while instantly cutting RAM usage in half across 1.3 million rows.

---

## 4.4 Module: `src/rainfall/audit.py`

### 4.4.1 Purpose
Performs quality auditing of raw meteorological distributions against official IMD portal benchmarks, evaluates calendar continuity (identifying missing days), and recomputes departures from normal rainfall.

### 4.4.2 Inputs & Outputs
* **Reads:** `data/interim/raw_full.parquet` and `config/config.yaml`.
* **Produces:** `outputs/reports/data_audit_full.md`, `outputs/tables/missing_days_by_month.csv`, and `outputs/tables/portal_comparison_full.csv`.

### 4.4.3 Mathematical Formula: Guarded Departure Calculation

In weather analytics, rainfall departure measures how far actual rainfall deviated from the long-term historical baseline:

$$\text{Departure \%} = \frac{\text{Actual Rainfall} - \text{Normal Rainfall}}{\text{Normal Rainfall}} \times 100$$

**The Zero-Baseline Problem:** If a desert district normally receives $0.02$ mm on an August day, and receives $2.0$ mm, raw division yields:
$$\frac{2.0 - 0.02}{0.02} \times 100 = +9,900\%$$
This mathematical explosion distorts statistical averages.

**The Code Guard (`src/rainfall/audit.py:125–129`):**

```python
def _recompute_departure(actual: pd.Series, normal: pd.Series, guard: float) -> pd.Series:
    out = (actual - normal) / normal * 100.0
    out = out.where(normal >= guard)
    return out
```

* **Explanation:** The `.where(normal >= guard)` condition masks out any day where `daily_normal_mm` is below 2.5 mm, setting the departure to `NaN` to maintain mathematical integrity.

### 4.4.4 Beginner Explanation & Viva Tip
> **In One Sentence:** `audit.py` tests whether our raw weather dataset matches published government statistics and checks for missing dates and corrupt numbers.
> **Professor Question:** *How many active dates exist in the dataset, and how do you handle missing calendar days?*
> **Student Answer:** The dataset spans 2021 to 2026 (2,088 calendar days). There are exactly 1,800 active observation dates and 288 missing days where no stations reported. Missing days are preserved as `NaN` and rendered with gray hatching on maps.

---

## 4.5 Module: `src/rainfall/names.py`

### 4.5.1 Purpose
Normalizes state and district text strings by removing punctuation, converting to uppercase/titlecase, stripping whitespace, and applying canonical alias replacements from `name_aliases.csv`.

### 4.5.2 Detailed Code Walkthrough (`src/rainfall/names.py:54–92`)

```python
def normalize_key(s: str) -> str:
    """Uppercase, strip punctuation, collapse whitespace."""
    if not isinstance(s, str) or not s.strip():
        return ""
    t = s.upper()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_district(dist: str, state: str | None = None) -> str:
    aliases = load_alias_maps()
    dist_clean = str(dist).strip() if dist is not None else ""
    if dist_clean in aliases["district_exact"]:
        return aliases["district_exact"][dist_clean]
    k = normalize_key(dist_clean)
    if k in aliases["district_norm"]:
        return aliases["district_norm"][k]
    return dist_clean


def district_key(state: str, district: str) -> str:
    """Stable composite key: STATE_STD::DISTRICT_STD."""
    return f"{normalize_state(state)}::{normalize_district(district, state)}"
```

### 4.5.3 Beginner Explanation & Viva Tip
> **In One Sentence:** `names.py` ensures that spelling differences like `"Baleshwar"` vs `"Balasore"` or `"Kancheepuram"` vs `"Kanchipuram"` are recognized as the exact same district.

---

## 4.6 Module: `src/rainfall/geo.py`

### 4.6.1 Purpose
Loads GIS vector boundaries (`districts_master.gpkg`, `india-soi.geojson`), validates geometry topology, repairs self-intersecting polygons, calculates spatial surface areas, and transforms Coordinate Reference Systems (CRS).

### 4.6.2 Key Concepts
* **EPSG:4326 (WGS 84):** Standard GPS latitude/longitude in degrees.
* **EPSG:7755 (India Equal Area):** Projected planar coordinate system measured in meters, used for accurate district surface area calculations ($km^2$).

### 4.6.3 Code Walkthrough (`src/rainfall/geo.py:50–75`)

```python
def _pct_valid(gdf: gpd.GeoDataFrame) -> float:
    if len(gdf) == 0:
        return 0.0
    return float(gdf.geometry.is_valid.mean() * 100.0)


def _standardize_gdf(gdf: gpd.GeoDataFrame, source_name: str) -> gpd.GeoDataFrame:
    # Ensure EPSG:4326 CRS
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    # Repair invalid geometries with buffer(0)
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)
    return gdf
```

---

## 4.7 Module: `src/rainfall/crosswalk.py`

### 4.7.1 Purpose
Links weather dataset district names to geographic polygon IDs in `districts_master.gpkg` using a multi-pass hierarchical algorithm (Manual $\rightarrow$ Exact $\rightarrow$ Normalized $\rightarrow$ RapidFuzz $\rightarrow$ Hungarian Assignment).

### 4.7.2 The 5 Matching Passes
1. **Pass 0 (Manual Overrides):** Reads `manual_overrides.csv` for known human-verified boundary swaps.
2. **Pass 1 (Exact Match):** Direct string equality between dataset name and polygon name inside the same state.
3. **Pass 2 (Normalized Match):** Strips punctuation, casing, and spaces.
4. **Pass 3 (RapidFuzz String Similarity):** Evaluates token ratio score. If score $\ge 92\%$, it auto-accepts the match.
5. **Pass 4 (Hungarian Algorithm):** For remaining unmatched districts in a state, constructs an $N \times M$ cost matrix based on string distance and solves the global assignment using `scipy.optimize.linear_sum_assignment`.

### 4.7.3 Real Code Walkthrough (`src/rainfall/crosswalk.py:165–200`)

```python
# Pass 4: Hungarian bipartite assignment
if unassigned_t and unassigned_p:
    cost_matrix = np.zeros((len(unassigned_t), len(unassigned_p)))
    for r_idx, ti in enumerate(unassigned_t):
        t_name = normalize_district(t_sub.loc[ti, "district"], state)
        for c_idx, pi in enumerate(unassigned_p):
            p_name = poly_dist_keys[pi]
            # RapidFuzz similarity converted to cost (lower cost = better match)
            score = fuzz.WRatio(t_name, p_name)
            cost_matrix[r_idx, c_idx] = 100.0 - score

    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    for r_i, c_i in zip(row_ind, col_ind):
        score = 100.0 - cost_matrix[r_i, c_i]
        if score >= min_assign:
            ti = unassigned_t[r_i]
            pid = poly_ids[unassigned_p[c_i]]
            assigned_poly.add(pid)
            matched_idx.add(ti)
            stats.fuzzy += 1
            rows.append({
                "dataset_state": t_sub.loc[ti, "state"],
                "dataset_district": t_sub.loc[ti, "district"],
                "shp_id": pid,
                "match_method": "hungarian",
                "match_score": float(score),
            })
```

---

## 4.8 Module: `src/rainfall/paint_groups.py`

### 4.8.1 Purpose
Resolves the **parent-child split district problem**. When a state carves a new modern district (present as a polygon in our 2026 LGD map) out of an older district (present in our historical weather dataset), `paint_groups.py` uses geometric spatial intersection to find which parent boundary contains $\ge 50\%$ of the child polygon and assigns the child the parent's weather data (`child_of_<Parent>`).

### 4.8.2 Code Walkthrough (`src/rainfall/paint_groups.py:50–85`)

```python
def assign_orphan_polygons(
    polygons: gpd.GeoDataFrame,
    crosswalk: pd.DataFrame,
    imd_gdf: gpd.GeoDataFrame | None = None,
) -> pd.DataFrame:
    # Identify polygons not directly matched by any dataset district
    matched_shp_ids = set(crosswalk.dropna(subset=["shp_id"])["shp_id"].astype(int))
    orphans = polygons[~polygons["shp_id"].isin(matched_shp_ids)].copy()

    # Spatial intersection against historical IMD parent boundaries
    if imd_gdf is not None and not orphans.empty:
        joined = gpd.sjoin(orphans, imd_gdf, how="left", predicate="intersects")
        # Compute geometric overlap area to find true parent (>= 50% containment)
        ...
```

* **Paint Group Summary on Disk:**
  * **731 Direct Matches:** Direct 1-to-1 link between dataset district and map polygon.
  * **28 Child Orphans:** Inherit parent district weather readings.
  * **24 No-Data Polygons:** Remote or unpopulated island/border fragments with no historical weather record, rendered with hatched no-data styling.

---

## 4.9 Module: `src/rainfall/dedupe.py`

### 4.9.1 Purpose
Resolves 42,258 duplicate district-date groups (same district reported more than once on the same date) using a deterministic 4-stage hierarchy: non-null selection $\rightarrow$ small-difference averaging $\rightarrow$ Queen spatial neighbor median $\rightarrow$ unresolvable NaN flagging.

### 4.9.2 Real Code Walkthrough (`src/rainfall/dedupe.py:61–78`)

```python
def _resolve_conflict(a: float, b: float, ref_r: float | None) -> tuple[float | None, str]:
    lo, hi = min(a, b), max(a, b)
    # Rule 1: Small difference (<2.0 mm or <20% of value) -> Average them
    if abs(a - b) <= max(2.0, 0.2 * hi):
        return (a + b) / 2.0, "conflict_mean_small"
    # Rule 2: No neighbor reference available -> Mark NaN
    if ref_r is None or np.isnan(ref_r):
        return None, "conflict_unresolvable_no_ref"
    da, db = abs(a - ref_r), abs(b - ref_r)
    thresh = max(25.0, 2.0 * abs(ref_r)) if ref_r else 25.0
    # Rule 3: Both values wildly far from neighbors -> Distrust or NaN
    if da > thresh and db > thresh:
        return None, "conflict_unresolvable_far"
    # Rule 4: Pick the value closest to spatial neighbor median
    return (a if da <= db else b), "conflict_neighbour_pick"
```

### 4.9.3 Deduplication Accounting Table

| Rule Category | Duplicate Groups Resolved | Action Taken |
| :--- | :--- | :--- |
| `non_null_actual` | 22,472 | Chose the record containing valid rainfall over `NaN` |
| `preferred_obj_id` | 13,926 | Chose primary station ID (`obj_id`) over secondary |
| `fallback` | 3,813 | Selected most complete metadata record |
| `conflict_mean_small` | 548 | Averaged near-identical readings ($\Delta < 0.5$ mm) |
| `conflict_neighbour_pick` | 504 | Selected reading matching surrounding spatial neighbors |
| `conflict_unresolvable_*` | 1,018 | Irreconcilable wild conflict; set to `NaN` and flagged in QC |
| **Total Duplicate Groups** | **42,258** | **Total rows reduced: 1,320,770 $\rightarrow$ 1,274,184** |

---

## 4.10 Module: `src/rainfall/hydrology_matrix.py`

### 4.10.1 Purpose
Computes complex hydrological indicators across 1.27M rows in under 2 seconds by converting the long table into a dense 2D NumPy array $[783 \text{ Paint Groups} \times 2088 \text{ Calendar Days}]$.

### 4.10.2 Features Computed by Matrix Engine
1. **Strict Rolling Sums (3-day, 7-day, 30-day):** Cumulative rainfall in window. If any day in the window is missing (`NaN`), the rolling sum is strictly preserved as `NaN` (no fake zero assumptions).
2. **Monsoon Cumulative Rainfall:** Sum of all rainfall since June 1st of each calendar year.
3. **Dry Spell Length:** Number of consecutive days with rainfall $< 2.5$ mm.
4. **Wet Spell Length:** Number of consecutive days with rainfall $\ge 2.5$ mm.
5. **Days Since Last Rain:** Counter tracking elapsed days since the last rainy day ($\ge 2.5$ mm).

### 4.10.3 Real Code Walkthrough (`src/rainfall/hydrology_matrix.py:50–66`)

```python
def rolling_sum_nan_strict(arr: np.ndarray, present: np.ndarray, window: int) -> np.ndarray:
    """Sum over window; NaN if any day in window missing or any actual NaN in window."""
    n_pg, n_d = arr.shape
    out = np.full_like(arr, np.nan, dtype=np.float32)
    for w in range(window - 1, n_d):
        sl = slice(w - window + 1, w + 1)
        block = arr[:, sl]
        pres = present[:, sl]
        ok = pres.all(axis=1) if window > 1 else pres
        with np.errstate(invalid="ignore"):
            sums = np.nansum(block, axis=1)
        sums[~ok] = np.nan
        out[:, w] = sums.astype(np.float32)
    return out
```

---

## 4.11 Module: `src/rainfall/classes.py`

### 4.11.1 Purpose
Implements official India Meteorological Department (IMD) classification rules for daily rainfall intensity and percentage departure categories.

### 4.11.2 IMD Daily Rainfall Intensity Bins

| Class Code | Category Label | Rainfall Range ($mm$) | Palette Color Hex |
| :--- | :--- | :--- | :--- |
| `0` | **No Rain** | $0.0\text{ mm}$ | `#EFEFEF` (Off-white) |
| `1` | **Very Light Rain** | $0.1 - 2.4\text{ mm}$ | `#B8D8F0` (Sky blue) |
| `2` | **Light Rain** | $2.5 - 15.5\text{ mm}$ | `#68A8D8` (Medium blue) |
| `3` | **Moderate Rain** | $15.6 - 64.4\text{ mm}$ | `#3878A8` (Royal blue) |
| `4` | **Heavy Rain** | $64.5 - 115.5\text{ mm}$ | `#204870` (Navy blue) |
| `5` | **Very Heavy Rain** | $115.6 - 204.4\text{ mm}$ | `#102840` (Midnight blue) |
| `6` | **Extremely Heavy Rain** | $\ge 204.5\text{ mm}$ | `#081820` (Dark navy) |
| `-1` | **No Data** | Missing / Null | `#D0D0D0` + `///` Hatching |

---

## 4.12 Module: `src/rainfall/render_daily.py` & `render_pool.py`

### 4.12.1 Purpose
Cartographic rendering engine that draws publication-grade daily choropleth maps (1500 $\times$ 1650 px @ 150 DPI) in parallel using RAM-aware multiprocessing.

### 4.12.2 Why Not `geopandas.plot()`?
Standard `geopandas.plot()` creates, draws, and destroys Matplotlib geometry objects on every iteration. For 1,800 days $\times$ 785 polygons, this takes ~10–15 seconds per frame (totaling $>6$ hours).

**The Frozen PolyCollection Solution:**
1. Polygons are converted into Matplotlib `Path` objects once during startup (`render_geom.py`).
2. A single `PolyCollection` is placed on the figure canvas.
3. For each date, the worker updates only the 1D facecolor array in memory and re-renders text elements (`DailyMapRenderer.draw_date()`).
4. Compresses directly to PNG using Pillow Zlib compression.
5. Achieves **under 0.35 seconds per map** (~10–15 minutes for all 1,800 maps).

### 4.12.3 Parallel Worker Sizing Formula (`src/rainfall/render_pool.py:69–75`)

$$\text{Workers} = \min\left(\text{CPU Cores} - 1, \left\lfloor \frac{\text{Available RAM (GB)} - 1.0}{0.59\text{ GB/worker}} \right\rfloor \right)$$

* **Why it matters:** On Windows systems, spawning too many worker processes causes sudden Out-of-Memory (OOM) crashes. This formula guarantees at least 1.0 GB of safety RAM headroom.

<!-- SECTION 4 COMPLETE -->
