# SECTION 5 — GEOMETRY AND CROSSWALK

---

## 5.1 Geographic Boundaries Architecture

A core strength of this project is its rigorous cartographic foundation. The repository integrates multiple official geospatial layers under `data/geo/`:

```
data/geo/
├── districts_master.gpkg                # Primary Local Government Directory (LGD 2026) boundaries (785 polygons)
└── candidates/
    ├── india-soi.geojson                # Official Survey of India (SOI) external national boundary outline
    ├── historical/                      # Reorganization tables (splits, carveouts, renames 1951–2024)
    │   ├── District_name_changes_1951_to_2021.csv
    │   ├── District_splits_and_carveouts_1951_to_2024.csv
    │   └── New_districts_created_1951_to_2024.csv
    ├── imd/                             # IMD 2024 reference polygon gist (749 features)
    └── india-geodata/                   # Bhuvan, LGD, and SOI Parquet/PMTiles sources
```

### 1. Master Layer: LGD 2026 (`districts_master.gpkg`)
* **Format:** OGC GeoPackage (`.gpkg`), layer name `"districts"`.
* **Features:** Exactly **785 district polygons**.
* **Coordinate Reference System (CRS):** `EPSG:4326` (WGS 84 latitude/longitude degrees).
* **Topology:** 100% valid geometry (zero self-intersections or unclosed rings; repaired with `buffer(0)` on load).
* **Attribute Columns:** `shp_id` (unique integer 0–784), `state_name`, `district_name`, `state_std`, `district_std`, `lgd_state_code`, `lgd_district_code`, `area_km2`, `centroid_lon`, `centroid_lat`.

### 2. National Boundary: Survey of India (`india-soi.geojson`)
* Official external boundary of the Republic of India provided by the Survey of India (SOI).
* Used as the master clipping boundary and background outline on all rendered daily maps.
* **Beige Fill Gap:** The union of all 785 district polygons covers $99.75\%$ of the SOI outline. Approximately $8,053\text{ km}^2$ (~$0.25\%$) along remote high-altitude glaciated crests or undefined border tracts is rendered in warm beige background (`#E8E4DC`) as documented in `ASSUMPTIONS.md`.

---

## 5.2 District Crosswalk Engine & Results

The link between meteorological records and geographic map polygons is stored in `data/processed/district_crosswalk.csv`.

### Crosswalk Matching Summary

| Match Method | Districts Matched | Description | Example |
| :--- | :--- | :--- | :--- |
| **`manual`** | 4 | Explicit human overrides from `config/manual_overrides.csv` | `Karnataka::Bengaluru Urban` $\rightarrow$ `shp_id 55` |
| **`exact`** | 682 | Exact string equality within the same state | `Maharashtra::Pune` $\rightarrow$ `shp_id 412` |
| **`normalized`** | 28 | Matched after stripping punctuation, casing, and spaces | `TAMIL NADU::Kancheepuram` $\rightarrow$ `Kanchipuram` (`shp_id 620`) |
| **`fuzzy` / `hungarian`** | 17 | RapidFuzz token match $\ge 92\%$ or global linear assignment | `Odisha::Baleshwar` $\rightarrow$ `Balasore` (`shp_id 512`) |
| **`unmatched`** | 4 | Placeholder records (e.g. `"Unknown Districts Of India"`) | Flagged in QC; excluded from maps |
| **Total** | **735** | **100% of real weather districts successfully mapped** | |

### Representative Real Rows from `data/processed/district_crosswalk.csv`

```csv
dataset_state,dataset_district,state_std,district_std,shp_id,match_method,match_score,needs_review,note
Karnataka,Bengaluru Rural,KARNATAKA,BENGALURU RURAL,54,manual,100.0,False,manual_overrides.csv
Karnataka,Bengaluru Urban,KARNATAKA,BENGALURU URBAN,55,manual,100.0,False,manual_overrides.csv
Maharashtra,Pune,MAHARASHTRA,PUNE,412,exact,100.0,False,exact match
Tamil Nadu,Kancheepuram,TAMIL NADU,KANCHIPURAM,620,normalized,100.0,False,alias dictionary
Odisha,Baleshwar,ODISHA,BALASORE,512,fuzzy,95.0,False,rapidfuzz token match
Andaman and Nicobar Islands,Unknown Districts Of India,ANDAMAN AND NICOBAR ISLANDS,UNKNOWN DISTRICTS OF INDIA,-1,unmatched,0.0,True,placeholder record
```

---

## 5.3 Paint Groups & Parent-Child Spatial Resolution

A major cartographic dilemma in historical meteorological analysis is administrative district splitting:
* The 2026 LGD map contains **785 modern polygons**.
* The 2021–2026 NDAP weather dataset contains **735 historical reporting entities**.

When a state carves a new district (such as *Hanamkonda* carved out of *Warangal* in Telangana), weather stations often continue reporting under the parent district name. If unhandled, the new child district polygon would appear as a blank "No Data" hole on the map.

### The Paint Group Resolution (`src/rainfall/paint_groups.py`):
1. **Direct Match:** If a polygon directly matches a dataset district, it receives a unique `paint_group_uid` (731 polygons).
2. **Spatial Containment Intersection:** For the remaining orphan polygons, the system intersects the child polygon with historical IMD boundaries. If a parent boundary contains $\ge 50\%$ of the child polygon, the child inherits the parent's weather data and is assigned the parent's `paint_group_uid` with resolution tag `child_of_<Parent>`.
3. **Automatic Cartographic Footnote:** When a daily map contains polygons rendered via parent values, `DailyMapRenderer` automatically adds an explanatory footnote:
   > *"Districts created after IMD reference map show their parent district's value."*
4. **No-Data Polygons (24 Polygons):** Remote uninhabited islands or disputed border fragments with zero historical weather data are assigned `paint_group_uid = -1` and rendered with diagonal gray hatching (`///`).

```
Total Map Polygons: 785
├── 731 Direct Paint Groups (1-to-1 match)
├── 28 Child Polygon Assignments (inherit parent data)
└── 24 Unassignable No-Data Polygons (hatched)
```

<!-- SECTION 5 COMPLETE -->
