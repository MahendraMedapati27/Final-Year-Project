# India district-wise rainfall maps (NDAP / IMD)

Reproducible pipeline for daily district choropleth maps and hydrology analytics from NDAP district rainfall CSV (2021–2026).

## Setup

```bash
cd "D:\final year project"
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
pip install -e .
```

Place data files (already expected):

- `data/raw/dataset_sample_5k.csv` — development sample
- `data/raw/dataset_full.csv` — full ~1.05M rows

## Commands (M0–M1)

```bash
python -m rainfall.cli --help
python -m rainfall.cli ingest --sample
python -m rainfall.cli audit --sample
python -m rainfall.cli audit          # full dataset (several minutes)
python -m rainfall.cli all --sample
```

Outputs: `data/interim/raw_*.parquet`, `outputs/reports/data_audit*.md`, `outputs/tables/*`.

## Daily map render (frozen layout, P5)

**Parity-approved** references: `outputs/maps/reference/approved_2026-09-19.png`, `approved_2021-01-31.png`. Do not change layout, colours, fonts, or stat/legend wording without a new parity pass.

### Re-run full daily maps

```powershell
cd "D:\final year project"
$env:PYTHONPATH = "$PWD\src"
# If `.venv\Scripts\python` fails with Application Control on pandas DLLs, use:
#   .\scripts\run_python.ps1 scripts\render\render_all_daily_maps.py
C:\ProgramData\anaconda3\python.exe scripts\render\render_all_daily_maps.py
```

- Output: `outputs/maps/daily_actual/YYYY/MM/rainfall_actual_YYYY-MM-DD.png` (~1,800 dates with data).
- Calendar gaps (288 days): `outputs/maps/missing_dates.csv`.
- Manifest: `outputs/maps/daily_actual/manifest.csv`.
- Progress / RAM: `logs/render_progress.log` (watchdog every 60 s).
- Errors: `logs/render_errors.csv`.
- Resumable: skips existing PNGs unless `--overwrite` (full render script uses overwrite for P5).

### Geometry cache (rebuild rule)

Workers load **`outputs/render_cache/<hash>/geometry.pkl`** only (no GPKG in worker processes). Rebuild when **`config/config.yaml`** `render.*` or boundary source changes:

```powershell
$env:PYTHONPATH = "$PWD\src"
python scripts/render/build_geometry_cache.py
```

Hash = `frozen_layout.render_config_hash()`.

### Workers and RAM

`worker_count()` ≈ `min(cpu_count−1, floor((available_GB − 1.0) / rss_per_worker_GB))` with **~0.59 GB/worker** (legacy pickle engine, measured after 3 frames). Engine: **`legacy_frozen_pillow`** (`render_engine.FrozenRenderer` + Pillow save).

### QA and contact sheet

```powershell
python scripts/verify/qa_all_maps.py          # all frames; use --sample 40 for dry-run
python scripts/verify/qa_contact_sheet.py     # after manifest exists
```

### Map notes

- **Beige gaps** outside district union but inside SOI outline: ~**0.25%** of outline area (`ASSUMPTIONS.md`, boundary file).
- **Parent value** footnote: districts painted from a parent aggregate when child geometry has no direct row (`child_of_*` resolution in paint groups).

See `ASSUMPTIONS.md`, `docs/CODE_LAYOUT.md`, and `scripts/README.md` for structure and decisions.
