# Scripts layout

## `pipeline/`

Data pipeline helpers (not daily render).

| Script | Purpose |
|--------|---------|
| `resume_enrich.py` | Resume M3 enrich after interruption |

## `render/`

Production map generation (frozen layout).

| Script | Purpose |
|--------|---------|
| `build_geometry_cache.py` | Build `outputs/render_cache/.../geometry.pkl` |
| `render_all_daily_maps.py` | All ~1,800 daily PNGs → `outputs/maps/daily_actual/` (skip existing unless `--overwrite`) |
| `render_reference_trials.py` | Re-render the two parity-approved reference dates |

## `verify/`

Post-render QA and data checks.

| Script | Purpose |
|--------|---------|
| `map_provenance.py` | PNG mtimes, PIL decode all frames |
| `map_parity_sample.py` | 60-date pixel compare vs current engine |
| `data_matrix_check.py` | Enriched parquet vs `render_matrix.npz` |
| `data_manifest_stats.py` | Manifest stats vs independent computation |
| `map_full_qa.py` | Full QA table over all frames |
| `maps_summary_and_contact_sheet.py` | Yearly summary CSV + contact sheet figure |
| `rerender_stale_maps.py` | Overwrite PNGs older than latest render code |
| `qa_all_maps.py` | Colour / manifest QA (use `--sample N` for dry-run) |
| `qa_maps_light.py` | File count / dimensions only |
| `qa_reference_parity.py` | Pixel parity vs `outputs/maps/reference/` |
| `qa_contact_sheet.py` | Contact sheet only (also in summary script) |
| `find_worst_layout_dates.py` | Pick dates for layout stress tests |

## `benchmarks/`

| Script | Purpose |
|--------|---------|
| `timing_slice_render.py` | Timing benchmark on a date slice |

## Root

| File | Purpose |
|------|---------|
| `run_python.ps1` | Windows helper when `.venv` pandas DLLs are blocked |

Main CLI remains **`python -m rainfall.cli`** (`src/rainfall/cli.py`).
