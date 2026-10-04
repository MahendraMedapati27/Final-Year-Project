# SECTION 8 — OUTPUTS AND VISUAL CARTOGRAPHY

---

## 8.1 Outputs Directory Structure

All deliverables produced by the system are organized under `outputs/`:

```
outputs/
├── checkpoints/                        # JSON checkpoint files documenting gate criteria
│   ├── part_a_gate.json                # Name agreement (90.28%) and IoU scores
│   ├── part_b_gate.json                # Row accounting (1,320,770 -> 1,274,184 rows)
│   ├── p5_full_render.json             # 1,800 maps rendered in 4,235 seconds (5.60 s/frame)
│   ├── p5_qa.json                      # Full QA test metrics
│   └── verify.json                     # 100% schema compliance verification
├── maps/
│   ├── daily_actual/                   # 1,800 rendered daily choropleth maps
│   │   ├── 2021/ ... 2026/             # High-resolution PNG files (1500 x 1650 px @ 150 DPI)
│   │   └── manifest.csv                # Complete map inventory and per-day statistics (10.5 KB)
│   ├── reference/                      # Approved reference gold standards (approved_2021-01-31.png)
│   └── trial/                          # Test render samples
├── render_cache/                       # Pickled PolyCollections for high-speed rendering (geometry.pkl)
├── reports/                            # Generated Markdown audit summaries and data dictionary
│   ├── data_audit_full.md
│   ├── data_dictionary.md
│   ├── duplicates_analysis.md
│   └── district_count_reconciliation.md
└── tables/                             # Aggregation Parquet files and analytical CSVs
    ├── national_daily.parquet
    ├── state_daily.parquet
    ├── district_monthly.parquet
    ├── district_season.parquet
    ├── district_annual.parquet
    └── duplicates_resolved.csv
```

---

## 8.2 The Master Manifest (`manifest.csv`)

The file `outputs/maps/daily_actual/manifest.csv` acts as the complete **auditable registry** for every rendered map.

### Real Rows from `outputs/maps/daily_actual/manifest.csv`

```csv
date,path,n_districts_with_data,n_no_data,n_parent_value,n_excluded_suspect,min_mm,max_mm,area_weighted_mean_mm,n_heavy,wettest_district,wettest_mm
2021-01-01,D:\final year project\outputs\maps\daily_actual\2021\01\rainfall_actual_2021-01-01.png,710,71,41,0,0.0,45.0,0.6925206859049426,0,"Tirunelveli, TAMIL NADU",45.0
2021-01-02,D:\final year project\outputs\maps\daily_actual\2021\01\rainfall_actual_2021-01-02.png,713,68,41,0,0.0,6.5,0.02055769829043768,0,"Lakshadweep District, LAKSHADWEEP",6.5
2021-01-03,D:\final year project\outputs\maps\daily_actual\2021\01\rainfall_actual_2021-01-03.png,703,78,39,0,0.0,24.2,0.4837355593872184,0,"New Delhi, DELHI",24.2
2021-01-05,D:\final year project\outputs\maps\daily_actual\2021\01\rainfall_actual_2021-01-05.png,694,87,40,0,0.0,65.8,1.3177369835592145,1,"Udhampur, JAMMU & KASHMIR",65.8
```

### Column-by-Column Meaning

| Manifest Column | Plain-English Meaning | Example |
| :--- | :--- | :--- |
| `date` | Calendar observation date of the map. | `2021-01-01` |
| `path` | Absolute on-disk path to the generated PNG image. | `.../rainfall_actual_2021-01-01.png` |
| `n_districts_with_data` | Number of districts with active gauge observations on this date. | `710` |
| `n_no_data` | Number of district polygons with missing data (rendered with hatching). | `71` |
| `n_parent_value` | Number of newly carved child districts painted using their parent district's reading. | `41` |
| `n_excluded_suspect` | Number of unverified sensor anomalies excluded from this date's map. | `0` |
| `min_mm` | Minimum measured rainfall among reporting districts. | `0.0` mm |
| `max_mm` | Maximum measured rainfall on this date. | `45.0` mm |
| `area_weighted_mean_mm` | National area-weighted average rainfall depth across India. | `0.69` mm |
| `n_heavy` | Number of districts receiving Heavy to Extremely Heavy rainfall ($\ge 64.5$ mm). | `0` |
| `wettest_district` | District receiving the highest rainfall on this date. | `"Tirunelveli, TAMIL NADU"` |
| `wettest_mm` | Rainfall depth recorded at the wettest district. | `45.0` mm |

---

## 8.3 Anatomical Walkthrough of a Rendered Daily Map

Let us inspect an actual rendered map: `outputs/maps/daily_actual/2026/09/rainfall_actual_2026-09-19.png` (Dimensions: $1500 \times 1650$ pixels @ 150 DPI).

```
+-------------------------------------------------------------------------------+
|  INDIA — DISTRICT DAILY RAINFALL (ACTUAL)                     19 Sep 2026     |
|  India Meteorological Department (IMD) / NDAP Observational Network           |
+-------------------------------------------------------------------------------+
|                                                                               |
|   +-------------------+                                                       |
|   | DAILY SUMMARY     |                                                       |
|   | Wettest District: |       MAIN MAP CANVAS (EPSG:4326)                     |
|   | Mawsynram (184mm) |                                                       |
|   | National Mean:    |       - 785 LGD District Polygons                     |
|   | 14.2 mm           |       - Survey of India Outer Boundary Outline        |
|   | Heavy Rain: 12    |       - Warm Beige Fill (#E8E4DC) for Outside Land    |
|   +-------------------+       - Official IMD Color Ramps (7 Bins)             |
|                                                                               |
|                                                                               |
|                                                                               |
|                                                                               +-------+
|                                                                               | A & N |
|                                                                               | Inset |
|   +-----------------------+                                                   +-------+
|   | LAKSHADWEEP INSET     |                                                   |
|   +-----------------------+                                                   |
+-------------------------------------------------------------------------------+
|  LEGEND: [ ] No Rain  [ ] 0.1-2.4mm  [ ] 2.5-15.5mm  [ ] 15.6-64.4mm  ...     |
|  FOOTNOTE: Districts created after IMD reference map show parent district value |
+-------------------------------------------------------------------------------+
```

### Visual Components Linked to Source Code:

1. **Title Header (`render_daily.py:215`):**
   * Displays *"INDIA — DISTRICT DAILY RAINFALL (ACTUAL)"* alongside the formatted date (`19 Sep 2026`) and data source attribution.
2. **Main Choropleth Canvas (`render_daily.py:277–340`):**
   * Renders all 785 district polygons inside the mainland extent $[68.0^\circ\text{E} - 97.5^\circ\text{E}, 6.5^\circ\text{N} - 37.5^\circ\text{N}]$.
   * State boundaries are drawn with dark, distinct borders (`#404040`) and district borders with subtle gray lines (`#A0A0A0`).
   * Areas outside the Survey of India outline are filled with warm beige (`#E8E4DC`).
3. **Dynamic Daily Summary Card (`render_daily.py:350–390`):**
   * Placed in the upper-left open Arabian Sea quadrant.
   * Displays the national area-weighted mean rainfall, count of heavy rainfall districts, and wettest district name and depth.
4. **Geographic Inset Boxes (`render_daily.py:423–460`):**
   * **Lakshadweep Inset:** Positioned in the lower-left ocean quadrant.
   * **Andaman & Nicobar Inset:** Positioned in the lower-right Bay of Bengal quadrant.
   * Each inset features its own border frame, localized bounding box, and scaled coordinate grid.
5. **Categorical Legend (`render_daily.py:240–270`):**
   * Displays all 7 official IMD color swatches with exact mm thresholds, plus the gray hatched patch for "No Data".
6. **Parent Footnote (`render_daily.py:395`):**
   * Automatically appears if newly carved child districts are present, providing full transparency to viewers.

<!-- SECTION 8 COMPLETE -->
