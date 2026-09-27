# Assumptions and decisions

## M0–M1 (initial)

| Topic | Decision |
|-------|----------|
| Project root | Workspace root (`final year project`), not a nested `india-rainfall/` folder |
| Parquet paths | `data/interim/raw_sample.parquet` and `data/interim/raw_full.parquet` |
| Column mapping | 25 columns by fixed order + regex on header text; assert count |
| Audit portal tolerance | 2% relative / 0.05 absolute for floats; exact for null counts |
| Duplicate resolution | Documented in audit; implementation deferred to M3 clean stage |
| Departure guard | `min_normal_mm_daily: 2.5` from config (recompute in audit for agreement only) |

## M1 audit findings (full CSV)

| Finding | Detail |
|---------|--------|
| Row count | **1,320,770** rows; differs from the ~1.05M quoted by the user — **cause unresolved** and does not affect analysis (removing 88,844 duplicate-key rows would still leave ~1.27M, not ~1.05M). Value statistics matching the portal confirm the correct file. |
| Value stats | All portal min/max/mean/median targets for rainfall fields **match** within tolerance |
| Null counts | `obj_id` and weekly/cumulative nulls are **~28k higher** than portal targets (787,174 vs 759,016 for `obj_id`); reason not fully explained |
| Calendar | **1,800** unique dates (2021-01-01 → 2026-09-19), **288** missing days in span |
| Duplicates | Must dedupe in M3 before maps |
| Category agreement | **97.66%** recomputed vs provided (guard normal ≥ 2.5 mm) |
| Departure recompute | Median abs diff **0.18 pp** where normal ≥ 2.5 mm |

## M2 geometry and crosswalk

| Topic | Decision |
|-------|----------|
| **Chosen boundaries** | **India Geodata `LGD_Districts.parquet`** (release `admin/districts`, March 2026). 785 districts, 100% valid geometry, 100% clean names. Beats datta07 on name quality (datta07 ~97% clean names, many corrupted labels) while meeting the ≥98% match gate (99.6% latest-date after aliases). |
| **India outline** | `data/geo/candidates/india-soi.geojson` from india-geodata (Survey of India external boundary — not OSM/Natural Earth). |
| **Simplification** | `shapely.coverage_simplify` at 0.007° failed on LGD topology; **fallback per-geometry `simplify`** with warning logged. |
| **LGD name table** | `districts.19Sep2026.csv` from ramSeraph/opendata release (reference only; geometry joined via LGD parquet codes). |
| **IMD 2024 gist** | Loads OK (749 features). **`id` overlaps dataset `Obj_Id` for 724/735 distinct IDs (~98.5%)** but is not used as primary geometry (missing newest AP districts vs LGD). |
| **guneetnarula 2019** | Not downloaded — repo contains **topojson only** (`https://github.com/guneetnarula/indian-district-boundaries/tree/master/topojson`). |
| **Merged districts (1 polygon, N dataset names)** | Policy **`area_weighted_mean`** at render time (config `merged_district_policy`); no many-to-one assignments in crosswalk (enforced by Hungarian + one-to-one). |
| **Placeholder** | `Unknown Districts Of India` flagged in crosswalk; exclude from maps in M4+. |

### Package versions (Windows venv, M2)

geopandas 1.1.4 · shapely **2.1.2** (coverage_simplify available; LGD layer still needed simplify fallback) · pyogrio 0.13.0 · pyproj 3.8.0 · matplotlib 3.11.2 · rapidfuzz 3.14.6

## Part A-fix (2026-09-20, evidence on disk)

| Topic | Decision / finding |
|-------|-------------------|
| **Obj_Id vs IMD 2024 gist names** | **90.28%** agreement on 741 distinct `(state, district, obj_id)` triples (`outputs/tables/obj_id_name_agreement.csv`). **72** disagree rows logged; **35** classified **(c)** (trust Obj_Id for naming — only these count against Obj_Id): 23 cross-state/name mismatches + 12 no gist feature. **37** **(b)** reorganisation since gist; **0** **(a)** pure spelling in classifier. |
| **IoU LGD vs IMD-by-Obj_Id** | Median **0.94**; **17** suspects → **13** after manual crosswalk overrides (`outputs/checkpoints/a_fix_iou.json`). Overrides: Bengaluru Rural/Urban shp swap, Paschim/Purba Medinipur shp swap (`config/manual_overrides.csv`). **Remaining 13**: mostly **legitimate split/merge** (stale 2024 gist geometry vs LGD 2026). **2** **wrong_match** (Pratapgarh RJ/UP): **LGD name crosswalk is correct**; IoU low because **IMD gist polygon for Obj_Id 29/380 does not align with LGD** — not fixed by shp override. |
| **772 vs 735 districts** | Raw **735** `(state, district)` keys; **732** excluding Unknown. Portal **772** not reproduced exactly; **4** district **names** appear in **>1** state (Bilaspur, Hamirpur, Pratapgarh, Unknown placeholder in 3 states). **730** unique district strings ignoring state (`outputs/reports/district_count_reconciliation.md`). |
| **Simplification** | **Unsimplified** LGD geometry. Measured PolyCollection draw **~1.14–1.24 s** for 785 parts at 150 dpi (**< 2 s** gate). |
| **Paint groups** | **731 direct**, **24 no_data**, remainder **child_of_*** orphans (`data/processed/paint_group_polygons.csv`). |

## M3 clean (Part B, 2026-09-20)

| Topic | Decision / finding |
|-------|-------------------|
| **Failed clean root cause** | Windows **OpenBLAS/thread oversubscription OOM** during large parquet writes; peak RSS **~1816 MB** at `write_enriched` (`logs/clean_memory.jsonl`). Mitigation: **`OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=4`** at top of `cli.py` before NumPy import. |
| **Dedupe** | Vectorised sort + `drop_duplicates`; **1,320,770 → 1,274,184** rows; **42,258** groups in `outputs/tables/duplicates_resolved.csv`. |
| **Calendar** | **2088** days in span; **1800** present; **288** missing (`outputs/tables/missing_days_by_month.csv`). |
| **Hydrology** | NumPy **paint_group × 2088** matrix (`hydrology_matrix.py`), not `groupby.rolling` on full long table. |
| **Enriched columns** | **54** columns in merged parquet (subset of full PROMPT §6 — additional QC/category recompute flags still in legacy `clean.py`, not all ported to `m3_clean.py`). Checkpoints: `data/processed/checkpoints/deduped.parquet`, `enriched_YYYY.parquet`. |
| **Aggregates** | `finalize` writes state/national daily + district month/season/year + JJAS coverage + `outputs/reports/data_dictionary.md`. |

## P1b follow-ups (2026-09-20)

| Topic | Decision |
|-------|----------|
| **Dedupe rule sum** | **42,258** groups = **42,235** named rules + **23** `non_null_actual` (the “missing 23”). **1,748** groups had **≥3** rows. |
| **Unresolvable conflicts** | **1,018** → NaN: only **4** had a neighbour reference `r`; **1,014** had no usable neighbour median. **NaN kept** (not arbitrary pick). Optional `conflict_distrust_pick` when both far but `r` exists (4 groups). |
| **Extreme >500 mm** | **19** district-days; **1** `isolated_suspect` (Jorhat 2022-07-26). Maps/aggregates use **`daily_actual_mm_map`** (NaN for that case only). Raw kept in `daily_actual_mm`. |
| **Historical CSVs** | Downloaded to `data/geo/candidates/historical/`. CSV name match assigns some orphans; **24** `no_data` remain where IMD containment & CSV parent both fail. |

## P1 data integrity (2026-09-20)

| Topic | Finding |
|-------|---------|
| **Fresh clean** | `clean --all --fresh` dedupe from `raw_full.parquet`; enrich resumed via `scripts/resume_enrich.py` after merge bug fix (resolution join duplicated rows). |
| **Row accounting** | **1,320,770 → 1,274,184** (−**46,586** = Σ(`n_in_group`−1) over **42,258** duplicate groups). |
| **verify** | `(district_uid, date)` unique, no negative rainfall, all PROMPT §6 columns present — `outputs/checkpoints/verify.json`. |
| **Dedupe conflicts** | No more `mean_conflict` mass averaging: **548** small-diff mean, **504** neighbour pick, **1018** unresolvable→NaN (`qc_dup_unresolvable`). |
| **772 vs 735** | **Unresolved** — portal count likely different rules; we document **735** `(state,district)` keys and move on. |
| **no_data LGD polygons** | **24** orphans; historical CSV files **not in repo** — assignment incomplete (`outputs/tables/no_data_polygons_report.csv`). |
| **SOI outside fill** | **~8,053 km²** (~**0.25%** of SOI outline) not covered by district union. |

## M4 trial maps (Part C, 2026-09-20)

| Topic | Decision |
|-------|----------|
| **Render matrix** | `data/processed/render_matrix.npz` — **1800 × 783** float32 values + int8 class index. |
| **Drawing** | Single figure **PolyCollection** on exploded parts; **no** `GeoDataFrame.plot()`. Outside fill **#E8E4DC**; hatched no-data. |
| **Trial outputs** | `outputs/maps/trial/rainfall_actual_2026-09-19.png` and wettest 2022–2025 day **2025-05-31** (max districts ≥64.5 mm). **1500×1650 px @ 150 dpi**. ~**5.9 s** per map (1 worker, measured). |

## P5 production render (frozen layout)

| Topic | Decision |
|-------|----------|
| **Engine** | **`legacy_frozen_pillow`** — pickle geometry cache + `DailyMapRenderer.draw_date` + Pillow PNG (`compress_level=1`). Parity **0%** pixels Δ>24 vs approved refs (`scripts/p3_parity.py`). |
| **Worker RSS** | **~605 MB** after init + 3 frames (~**0.59 GB/worker**); formula leaves **1 GB** headroom (`render_pool.worker_count`). |
| **Layout QA** | Data-driven worst dates (`scripts/find_worst_layout_dates.py`); overlap test checks **dynamic text only** (stats/title/footer). Legend inset is fixed on-map (parity-approved; may overlap low-res land mask). |
| **Python on Windows** | Some shells block `.venv` pandas DLLs via Application Control — use **`scripts/run_python.ps1`** (Anaconda base) for render/QA. |
