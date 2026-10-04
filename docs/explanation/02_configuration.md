# SECTION 2 — CONFIGURATION DEEP DIVE

---

## 2.1 Configuration Architecture

Configuration files allow the system to change its behavior, adjust mathematical thresholds, update file paths, or fix geographic spelling variations **without modifying a single line of Python source code**.

The repository contains three primary configuration files located under the `config/` directory:

1. `config/config.yaml`: The master settings file governing file paths, data audit validation bounds, hydrological calculation thresholds, color palette hex codes, and cartographic map layout parameters.
2. `config/name_aliases.csv`: A dictionary of 136 known spelling variations, old historical names, and typographical differences between the weather portal records and modern GIS map boundaries.
3. `config/manual_overrides.csv`: An explicit, deterministic override table that maps ambiguous district names directly to specific polygon IDs (used to correct algorithm swaps such as Bengaluru Urban vs. Rural).

---

## 2.2 Deep Dive: `config/config.yaml`

### Purpose & Consumer
* **File Path:** `config/config.yaml`
* **Loaded By:** `src/rainfall/config.py` via `load_config()`, and subsequently consumed by almost every pipeline module (`io.py`, `audit.py`, `crosswalk.py`, `dedupe.py`, `render_daily.py`, `render_geom.py`, and `render_pool.py`).

### Key Configuration Sections and Real Values

Below are the actual sections from `config/config.yaml` on disk:

```yaml
paths:
  raw_csv_sample: data/raw/dataset_sample_5k.csv
  raw_csv_full: data/raw/dataset_full.csv
  interim_parquet: data/interim/raw.parquet
  processed_enriched: data/processed/rainfall_enriched.parquet
  geo_districts: data/geo/districts_master.gpkg
  render_matrix: data/processed/render_matrix.npz
  crosswalk: data/processed/district_crosswalk.csv
  name_aliases: config/name_aliases.csv
  manual_overrides: config/manual_overrides.csv

outputs:
  maps_daily_actual: outputs/maps/daily_actual
  videos: outputs/videos
  tables: outputs/tables
  figures: outputs/figures
  reports: outputs/reports

audit:
  portal_daily_actual_min: 0
  portal_daily_actual_max: 1225
  portal_daily_actual_mean: 3.81
  portal_daily_actual_median: 0.0
  portal_daily_normal_max: 935
  portal_daily_normal_mean: 3.94
  portal_daily_normal_median: 1.40
  portal_daily_departure_min: -300
  portal_daily_departure_max: 99900
  portal_daily_departure_mean: 117.91
  portal_daily_departure_median: -100
  portal_cumulative_actual_max: 16500
  portal_cumulative_actual_mean: 622.75
  portal_cumulative_actual_median: 312.30

hydrology:
  min_normal_mm_daily: 2.5
  min_normal_mm_cumulative: 5.0
  rainy_day_threshold_mm: 2.5
  heavy_rain_threshold_mm: 64.5
  very_heavy_rain_threshold_mm: 115.6
  extreme_rain_threshold_mm: 204.5
  rolling_windows: [3, 7, 30]

render:
  dpi: 150
  figure_size: [10.0, 11.0] # 1500 x 1650 pixels
  main_map_extent: [68.0, 97.5, 6.5, 37.5] # [min_lon, max_lon, min_lat, max_lat]
  crs: "EPSG:4326"
  palette:
    no_rain: "#EFEFEF"       # 0.0 mm (Off-white / light grey)
    very_light: "#B8D8F0"    # 0.1 - 2.4 mm (Soft sky blue)
    light: "#68A8D8"         # 2.5 - 15.5 mm (Medium blue)
    moderate: "#3878A8"      # 15.6 - 64.4 mm (Deep royal blue)
    heavy: "#204870"         # 64.5 - 115.5 mm (Navy blue)
    very_heavy: "#102840"    # 115.6 - 204.4 mm (Dark midnight blue)
    extremely_heavy: "#081820" # >= 204.5 mm (Near black navy)
    no_data: "#D0D0D0"       # Gray with diagonal hatching
    outside_india: "#E8E4DC" # Warm beige background fill for areas outside Indian border
```

### Detailed Field Explanation & Impact

| Parameter | Type | Default Value | Plain-English Meaning & Impact | Failure / Breakage Risk |
| :--- | :--- | :--- | :--- | :--- |
| `paths.raw_csv_full` | String | `data/raw/dataset_full.csv` | Specifies the location of the primary raw weather dataset. | If the path is wrong or the file is missing, ingestion halts immediately with a `FileNotFoundError`. |
| `audit.portal_daily_actual_max` | Float | `1225` | Expected maximum single-day rainfall (in mm) based on official IMD portal documentation. | Used by `audit.py` to ensure the downloaded dataset has not been corrupted or altered. |
| `hydrology.min_normal_mm_daily` | Float | `2.5` | Mathematical guard baseline for departure calculations. | **Why it matters:** In arid regions or dry seasons, normal daily rainfall might be $0.01$ mm. If actual rainfall is $2$ mm, the raw formula $(2 - 0.01) / 0.01 \times 100 = +19,900\%$ yields an absurd mathematical explosion. The 2.5 mm guard sets departure to `NaN` or undefined when normal rainfall is below 2.5 mm. |
| `hydrology.rolling_windows` | List | `[3, 7, 30]` | Defines the moving window sizes (in consecutive days) used to calculate cumulative soil moisture and rainfall accumulation. | Changing this list (e.g., adding `14`) automatically creates new columns (`rain_14d_mm`) in the hydrology engine. |
| `render.dpi` | Integer | `150` | Rendering resolution (dots per inch). | Combined with `figure_size: [10.0, 11.0]`, it produces exactly $1500 \times 1650$ pixel maps. Increasing to 300 DPI quadruples memory consumption and rendering time. |
| `render.palette.*` | Hex Strings | `#EFEFEF`, `#B8D8F0`... | The exact color codes assigned to each rainfall intensity bin. | Must adhere to CIELAB perceptual uniformity and colorblind accessibility rules validated by `palette_lab.py`. |

---

## 2.3 Deep Dive: `config/name_aliases.csv`

### Purpose & Consumer
* **File Path:** `config/name_aliases.csv` (136 lines)
* **Loaded By:** `src/rainfall/names.py` via `load_alias_maps()`, and consumed by `crosswalk.py` during district name matching.

### Why It Is Needed
Weather data collected over decades often uses historical, colonial, or phonetic spellings, whereas modern GIS boundaries follow official Local Government Directory (LGD 2026) standards. Without an alias dictionary, hundreds of valid district weather records would fail to match map polygons.

### Representative Real Rows

```csv
type,dataset_value,canonical_value,note
state,The Dadra and Nagar Haveli and Daman and Diu,DADRA AND NAGAR HAVELI AND DAMAN AND DIU,shapefile variant
district,Y.S.R.,YSR Kadapa,AP rename
district,Leh Ladakh,Leh,UT
district,Baleshwar,Balasore,Odisha spelling
district,Kancheepuram,Kanchipuram,Tamil Nadu phonetic variant
district,Belagavi,Belgaum,Karnataka official rename
district,Prayagraj,Allahabad,UP historical name
district,Nabarangpur,Nabarangapur,Odisha spelling
district,S.P.S. Nellore,Sri Potti Sriramulu Nellore,AP full title
```

### Explanation of Columns
1. **`type`:** Indicates whether the alias applies to a `state` or a `district`.
2. **`dataset_value`:** The exact string as it appears in the raw NDAP weather CSV.
3. **`canonical_value`:** The standardized, official name used in the GIS boundary layer (`districts_master.gpkg`).
4. **`note`:** A human-readable comment explaining why the alias exists (e.g., state reorganization, spelling reform, or administrative renaming).

---

## 2.4 Deep Dive: `config/manual_overrides.csv`

### Purpose & Consumer
* **File Path:** `config/manual_overrides.csv`
* **Loaded By:** `src/rainfall/crosswalk.py` via `load_manual_overrides()`.

### Why It Is Needed
Automated string matching and bipartite optimization (Hungarian algorithm) can occasionally swap neighboring districts with nearly identical names and equal spatial proximity. For example, in Karnataka, `Bengaluru Rural` and `Bengaluru Urban` share almost identical text tokens. In early automated runs, the Hungarian matching swapped their polygon assignments, leading to an Intersection-over-Union (IoU) spatial failure. `manual_overrides.csv` acts as an absolute, inviolable override that forces specific dataset names to bind to exact polygon IDs before automated matching begins.

### Complete Real Rows

```csv
# Manual crosswalk overrides — always win over automatic matching.
# Edit rows below: dataset_state and dataset_district must match the rainfall CSV exactly; shp_id = polygon id in districts_master.gpkg.
dataset_state,dataset_district,shp_id,note
Karnataka,Bengaluru Rural,54,IoU fix: was swapped with Urban (hungarian)
Karnataka,Bengaluru Urban,55,IoU fix: was swapped with Rural
West Bengal,Paschim Medinipur,770,IoU fix: manual polygon alignment
West Bengal,Purba Medinipur,771,IoU fix: manual polygon alignment
```

### What Happens If Misconfigured?
If a user inputs an invalid `shp_id` (e.g., polygon ID `9999` which does not exist in `districts_master.gpkg`), `crosswalk.py` raises an assertion error during validation, preventing corrupted spatial mappings from propagating into the rendering engine.

<!-- SECTION 2 COMPLETE -->
