# Data audit (sample)

- Rows: **5,000** | Columns: **26** | Memory (deep): **0.9 MB**
- Date range: 2026-09-13 → 2026-09-19 (7 unique dates)
- Missing calendar days in span: **0**

## Portal metadata comparison
| metric                   |    computed |    portal | kind       | match   |
|:-------------------------|------------:|----------:|:-----------|:--------|
| daily_actual_min         |     0       |      0    | min        | True    |
| daily_actual_max         |   141.2     |   1225    | max        | False   |
| daily_actual_mean        |     4.67603 |      3.81 | mean       | False   |
| daily_actual_median      |     0.6     |      0    | median     | False   |
| daily_normal_max         |    44.3     |    935    | max        | False   |
| daily_normal_mean        |     6.10082 |      3.94 | mean       | False   |
| daily_normal_median      |     5.4     |      1.4  | median     | False   |
| departure_min            |  -100       |   -300    | min        | False   |
| departure_max            | 66900       |  99900    | max        | False   |
| departure_mean           |    24.5358  |    117.91 | mean       | False   |
| departure_median         |   -88       |   -100    | median     | False   |
| cumulative_actual_max    |  3138.3     |   5036    | max        | False   |
| cumulative_actual_median |   635.2     |     66.1  | median     | False   |
| monthly_actual_min       |     0       |     -4    | min        | False   |
| monthly_actual_max       |   482.6     |   4944    | max        | False   |
| obj_id_null              |     0       | 759016    | null_count | False   |
| weekly_date_null         |     0       | 764227    | null_count | False   |
| weekly_category_null     |     0       | 759017    | null_count | False   |
| cumulative_date_null     |     0       | 759658    | null_count | False   |
| cumulative_category_null |     0       | 759016    | null_count | False   |

## Null counts (selected)
|                                   |   0 |
|:----------------------------------|----:|
| country                           |   0 |
| state                             |   0 |
| district                          |   0 |
| year_label                        |   0 |
| calendar_day_raw                  |   0 |
| obj_id                            |   0 |
| daily_category_provided           |   0 |
| weekly_date_raw                   |   0 |
| weekly_category_provided          |   0 |
| cumulative_date_raw               |   0 |
| cumulative_category_provided      |   0 |
| monthly_date_raw                  |   0 |
| monthly_category_provided         |   0 |
| daily_actual_mm                   |  14 |
| daily_normal_mm                   |  14 |
| daily_departure_pct_provided      |  88 |
| weekly_actual_mm_provided         |  14 |
| weekly_normal_mm_provided         |  14 |
| weekly_departure_pct_provided     |  76 |
| cumulative_actual_mm_provided     |  14 |
| cumulative_normal_mm_provided     |  14 |
| cumulative_departure_pct_provided |  61 |
| monthly_actual_mm_provided        |  14 |
| monthly_normal_mm_provided        |  14 |
| monthly_departure_pct_provided    |  61 |

## Duplicates on (state, district, date)
- Duplicate rows: **36** (18 groups)

## Value QC summary
- Negative daily actual: 0
- Zero daily actual: 1965
- Extreme (>500.0 mm): 0
- Daily actual max: 141.1999969482422 mm

## Departure recompute (normal >= {guard} mm)
|                    |           0 |
|:-------------------|------------:|
| n_comparable       | 4181        |
| median_abs_diff_pp |    0.157898 |
| mean_abs_diff_pp   |    0.476731 |
| pct_within_1pp     |   93.614    |

## Category agreement (recomputed vs provided): **96.40%**

## Weekly actual vs daily (by date, % equal)
|       |        n |   pct_weekly_eq_daily |
|:------|---------:|----------------------:|
| count |   7      |               7       |
| mean  | 714.286  |              58.172   |
| std   |  36.7592 |              50.1005  |
| min   | 631      |               3.69863 |
| 25%   | 726.5    |               5.11497 |
| 50%   | 727      |              94.9246  |
| 75%   | 729.5    |              99.381   |
| max   | 730      |              99.589   |

## Consistency checks
- Normal stability (same DOY multiple values): {'groups': 4982, 'groups_multiple_normals': 11, 'pct_unstable': np.float64(0.22079486150140507)}
- Cumulative vs daily sum: {'n_checks': 726, 'pass_rate_pct': 0.6887052341597797}
- Monthly vs daily sum: {'n_checks': 726, 'pass_rate_pct': 9.641873278236915}

## Known issues register
1. Duplicate keys resolved in clean stage (prefer non-null actual; richer obj_id history).
2. Departure % unreliable when normal ≈ 0; recompute with guard.
3. Categories recomputed from guarded departure; provided kept.
4. Weekly columns often equal daily — not rolling 7-day; compute own rolling sums.
5. Obj_Id not a shapefile key; missing ~72% in full data.
6. District/state name variants require crosswalk + aliases.
