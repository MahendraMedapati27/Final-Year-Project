# SECTION 11 — PROFESSOR & VIVA DEFENSE PREPARATION

---

## 11.1 Basic Project Questions

### Q1: What is the core objective of this project?
* **Short Answer:** It is an automated data engineering and hydrological mapping pipeline that cleans messy meteorological records from 700+ Indian districts across 2021–2026 and generates 1,800 publication-grade daily choropleth maps and analytical datasets.
* **Detailed Explanation:** Raw government weather datasets suffer from name mismatches, duplicate entries with conflicting numbers, sensor anomalies, and missing dates. Generating thousands of maps manually is impossible. This system automates ingestion, cleaning, geographic reconciliation with modern 2026 boundaries, multi-day rolling hydrological calculations, and parallel map rendering with zero human intervention.

### Q2: Why is automated daily rainfall mapping useful?
* **Short Answer:** It provides instant, auditable spatial intelligence for agricultural planning, flood risk monitoring, and drought progression tracking across India.
* **Detailed Explanation:** Tabular spreadsheets with 1.3 million rows are difficult to interpret. Converting numbers into daily visual maps with official IMD color ramps allows policy makers, agronomists, and disaster response teams to immediately see where monsoon depressions are moving or where dry spells are threatening crops.

---

## 11.2 Data & Cleaning Questions

### Q3: Where did the raw data come from, and how large is it?
* **Short Answer:** Sourced from the National Data and Analytics Platform (NDAP) / India Meteorological Department (IMD). The raw CSV is ~213 MB, containing 1,320,770 rows and 25 raw columns.
* **Detailed Explanation:** After ingesting into Parquet and resolving 42,258 duplicate district-date groups, the clean dataset contains exactly 1,274,184 rows spanning January 1, 2021 to September 19, 2026 across 1,800 active observation dates.

### Q4: How does your pipeline resolve duplicate district-date records?
* **Short Answer:** Using a 4-tier deterministic hierarchy: non-null selection $\rightarrow$ small-difference averaging $\rightarrow$ Queen spatial neighbor comparison $\rightarrow$ unresolvable `NaN` flagging.
* **Detailed Explanation:** When multiple records exist for the same district and date, the code first picks non-null actual values. If two different numbers exist: if the difference is $<0.5$ mm, it averages them; if large, it compares them against the median rainfall of surrounding Queen spatial neighbor districts to pick the most plausible reading. Wild conflicts with no neighbor data are set to `NaN` and flagged in QC logs.

### Q5: What is the "departure guard" and why is it necessary?
* **Short Answer:** A 2.5 mm baseline threshold that prevents division-by-near-zero mathematical explosions when calculating percentage departure from normal rainfall.
* **Detailed Explanation:** Departure formula is $\frac{\text{Actual} - \text{Normal}}{\text{Normal}} \times 100$. If normal daily rainfall is $0.01$ mm and actual rain is $2$ mm, the formula outputs $+19,900\%$, which distorts statistical averages. The guard sets departure to `NaN` whenever normal daily rainfall is below 2.5 mm.

---

## 11.3 GIS & Algorithm Questions

### Q6: How do you match weather district names to map polygons?
* **Short Answer:** Using a multi-pass matching engine: Manual Overrides $\rightarrow$ Exact Match $\rightarrow$ Normalized Match $\rightarrow$ RapidFuzz Fuzzy String Matching $\rightarrow$ Hungarian Optimization Algorithm.
* **Detailed Explanation:** Weather portals use historical or phonetic names (e.g., `"Baleshwar"`), while modern GIS boundaries use LGD 2026 standards (`"Balasore"`). The system cleans text, applies a 136-alias dictionary, accepts fuzzy token similarity $\ge 92\%$, and uses the Hungarian bipartite algorithm (`scipy.optimize.linear_sum_assignment`) to find the globally optimal 1-to-1 match per state.

### Q7: What happens when a modern map district was created after the weather dataset began?
* **Short Answer:** We use "Paint Groups" and spatial intersection to assign the newly carved child polygon the weather reading of its parent district (`child_of_<Parent>`).
* **Detailed Explanation:** When a state carves a new district (e.g., *Hanamkonda* from *Warangal*), weather stations often continue reporting under the parent district name. Our code intersects the child polygon with historical IMD boundaries. If a parent contains $\ge 50\%$ of the child, the child inherits the parent's data, and an explanatory footnote is automatically placed on the map.

### Q8: What is the Hungarian Algorithm and why did you use it?
* **Short Answer:** A combinatorial optimization algorithm that solves the assignment problem in polynomial time, ensuring the best global pairing of dataset names to map polygons without duplicate assignments.
* **Detailed Explanation:** Greedy matching can match the first district to a polygon and leave the second district with no valid option. The Hungarian algorithm considers all possible pairings inside a state simultaneously, minimizing total string edit distance across the entire state.

---

## 11.4 Software Engineering & Performance Questions

### Q9: Why did you convert raw CSV into Apache Parquet?
* **Short Answer:** Parquet cuts disk size by 94% (213 MB $\rightarrow$ 12.3 MB), loads in under 0.8 seconds, preserves binary data types natively, and allows reading specific columns without loading the entire table.
* **Detailed Explanation:** CSV files are text-based and require slow parsing on every load. Parquet is a columnar binary format with Snappy/Zstd compression that enables predicate pushdown and efficient memory utilization.

### Q10: Why is your map rendering so fast compared to `geopandas.plot()`?
* **Short Answer:** We pre-compute all 785 polygon paths into a pickled Matplotlib `PolyCollection` once, and parallel worker processes simply update the 1D facecolor array in memory per frame.
* **Detailed Explanation:** Standard `geopandas.plot()` builds and destroys geometry objects on every iteration, taking 10–15 seconds per map. Our custom `DailyMapRenderer` loads the pre-exploded geometry cache into memory once, taking under 0.35 seconds per map and saving directly via Pillow Zlib compression.

### Q11: How do you prevent Out-of-Memory (OOM) crashes during multi-core rendering?
* **Short Answer:** By dynamically calculating the worker count based on available system RAM (~0.59 GB per worker) with a mandatory 1.0 GB safety headroom.
* **Detailed Explanation:** The formula $\min(\text{CPU} - 1, \lfloor (\text{RAM} - 1.0) / 0.59 \rfloor)$ guarantees that the multi-processing pool never exceeds physical memory limits on Windows machines.

---

## 11.5 Critical-Thinking & Limitation Questions

### Q12: How do you handle missing days when calculating 3-day or 7-day rolling rainfall?
* **Short Answer:** We strictly output `NaN`. We do NOT assume missing days are zero.
* **Detailed Explanation:** Assuming missing days are zero would falsely diagnose a drought, while filling with averages creates fake flood peaks. Scientific integrity requires strictly preserving `NaN` if any day in the moving window is missing.

### Q13: If you had another 3 months to work on this project, what would you improve?
* **Short Answer:** I would integrate real-time satellite precipitation interpolation (like NASA GPM/IMERG) to fill the 288 missing days, add automated weather station (AWS) telemetric feeds to disaggregate parent-child split districts, and build an interactive web dashboard.

<!-- SECTION 11 COMPLETE -->
