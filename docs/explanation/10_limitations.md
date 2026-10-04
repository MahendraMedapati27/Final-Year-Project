# SECTION 10 — LIMITATIONS AND ARCHITECTURAL ASSUMPTIONS

---

## 10.1 Real-World Data & System Limitations

Every genuine engineering project working with real-world government datasets has real limitations. In a project defense or viva, openly discussing these trade-offs demonstrates deep scientific maturity.

Below are the **7 verified architectural limitations and assumptions** documented in `ASSUMPTIONS.md` and repository audit reports:

---

### 1. Row Count & District Discrepancy
* **The Issue:** The raw CSV contains **1,320,770 rows** and **735 distinct (state, district) keys**, whereas preliminary portal summaries cited ~1.05M rows and 772 districts.
* **Why It Happens:** NDAP and IMD periodically restructure administrative tables and add historical back-casts. In addition, 4 district names in India appear across multiple states (e.g., *Bilaspur* in Himachal Pradesh vs. Chhattisgarh; *Hamirpur* in HP vs. UP; *Pratapgarh* in Rajasthan vs. UP), and placeholder `"Unknown Districts Of India"` entries exist across 3 Union Territories.
* **Current Handling:** The system strictly reconciles the raw 735 keys. Removing 46,586 duplicate rows yields exactly **1,274,184 clean records** with value statistics matching portal targets.
* **Future Enhancement:** Establish a real-time API sync with the National Data and Analytics Platform to ingest versioned changelogs.

---

### 2. Missing Calendar Days (288 Gap Dates)
* **The Issue:** Between January 1, 2021 and September 19, 2026 (2,088 calendar days), exactly **1,800 active observation dates** exist, leaving **288 missing days**.
* **Why It Happens:** Data transmission blackouts, server maintenance at the central meteorological repository, or non-reporting national holidays.
* **Current Handling:** The system does NOT invent fake numbers or assume 0.0 mm of rainfall. Missing dates are preserved as `NaN`, documented in `outputs/tables/missing_days_by_month.csv`, and rendered with gray diagonal hatching on maps.
* **Future Enhancement:** Implement spatial kriging or satellite precipitation interpolation (such as NASA GPM / IMERG) to fill regional reporting blackouts.

---

### 3. Parent-District Painting for Newly Carved Polygons
* **The Issue:** The 2026 LGD map contains 785 modern district polygons, but the historical weather dataset contains 735 reporting entities.
* **Why It Happens:** When a state carves a new district (such as *Hanamkonda* carved out of *Warangal* in Telangana), weather gauges often continue reporting under the historical parent name for several years before new administrative station IDs are assigned.
* **Current Handling:** Child polygons inherit the parent's weather data (`child_of_<Parent>`), and `DailyMapRenderer` places a transparent explanatory footnote on the map canvas.
* **Impact:** 28 child districts show their parent's rainfall rather than localized micro-climate data.
* **Future Enhancement:** Incorporate localized automatic weather station (AWS) telemetric feeds to disaggregate rainfall within split districts.

---

### 4. Unassignable No-Data Polygons (24 Polygons)
* **The Issue:** Exactly **24 map polygons** remain completely unassigned (`paint_group_uid = -1`).
* **Why It Happens:** These represent remote uninhabited island rocks (such as offshore shoals in Andaman & Nicobar, Lakshadweep) or narrow border boundary fragments where neither spatial containment ($\ge 50\%$) nor historical parent crosswalks could establish a valid weather link.
* **Current Handling:** Explicitly cataloged in `outputs/tables/no_data_polygons_report.csv` and rendered with gray hatching (`///`).

---

### 5. Boundary Fill Gap with Survey of India (0.25% Area)
* **The Issue:** The geometric union of all 785 LGD district polygons covers $99.75\%$ of the official Survey of India external boundary, leaving approximately $8,053\text{ km}^2$ (~$0.25\%$) of unassigned border area.
* **Why It Happens:** High-altitude glaciated crests, salt marshes (Rann of Kutch), or undefined territorial tracts in the Survey of India outline that do not fall within any designated civil district boundary.
* **Current Handling:** Rendered with a warm beige background fill (`#E8E4DC`) behind the district polygons.

---

### 6. Strict Missing Data Policy in Rolling Hydrology
* **The Issue:** If even a single day inside a 3-day or 7-day moving window has missing data (`NaN`), the rolling sum (`rain_3d_mm`, `rain_7d_mm`) strictly outputs `NaN`.
* **Why It Happens:** In scientific hydrology, guessing a missing day as $0.0$ mm causes false drought diagnoses, while guessing it as the monthly average distorts flash flood metrics.
* **Impact:** Rolling metrics contain `NaN` gaps during calendar blackout periods.

---

### 7. Extreme Value Handling (>500 mm Gauge Outliers)
* **The Issue:** Rare single-day rainfall readings exceed $500$ mm (e.g., Jorhat on 2022-07-26 reporting 850 mm).
* **Why It Happens:** Sensor calibration errors or gauge decimal point entry errors.
* **Current Handling:** `extremes.py` audits surrounding Queen spatial neighbors. If neighboring districts all recorded $<5$ mm, the event is flagged as `isolated_suspect`, preserved in raw `daily_actual_mm` for provenance, but set to `NaN` in `daily_actual_mm_map` so maps do not display deceptive anomalies.

<!-- SECTION 10 COMPLETE -->
