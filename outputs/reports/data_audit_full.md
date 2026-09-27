# Data audit (full)

- Rows: **1,320,770** | Columns: **26** | Memory (deep): **187.6 MB**
- Date range: 2021-01-01 → 2026-09-19 (1800 unique dates)
- Missing calendar days in span: **288**

## Portal metadata comparison
| metric                   |     computed |    portal | kind       | match   |
|:-------------------------|-------------:|----------:|:-----------|:--------|
| daily_actual_min         |      0       |      0    | min        | True    |
| daily_actual_max         |   1224.8     |   1225    | max        | True    |
| daily_actual_mean        |      3.80788 |      3.81 | mean       | True    |
| daily_actual_median      |      0       |      0    | median     | True    |
| daily_normal_max         |    935.3     |    935    | max        | True    |
| daily_normal_mean        |      3.93535 |      3.94 | mean       | True    |
| daily_normal_median      |      1.4     |      1.4  | median     | True    |
| departure_min            |   -300       |   -300    | min        | True    |
| departure_max            |  99900       |  99900    | max        | True    |
| departure_mean           |    117.909   |    117.91 | mean       | True    |
| departure_median         |   -100       |   -100    | median     | True    |
| cumulative_actual_max    |   5035.9     |   5036    | max        | True    |
| cumulative_actual_median |     66.1     |     66.1  | median     | True    |
| monthly_actual_min       |     -4       |     -4    | min        | True    |
| monthly_actual_max       |   4944.3     |   4944    | max        | True    |
| obj_id_null              | 787174       | 759016    | null_count | False   |
| weekly_date_null         | 793153       | 764227    | null_count | False   |
| weekly_category_null     | 787175       | 759017    | null_count | False   |
| cumulative_date_null     | 788464       | 759658    | null_count | False   |
| cumulative_category_null | 787174       | 759016    | null_count | False   |

## Null counts (selected)
|                                   |      0 |
|:----------------------------------|-------:|
| country                           |      0 |
| state                             |      0 |
| district                          |      0 |
| year_label                        |      0 |
| calendar_day_raw                  |      0 |
| obj_id                            | 787174 |
| daily_category_provided           |      0 |
| weekly_date_raw                   | 793153 |
| weekly_category_provided          | 787175 |
| cumulative_date_raw               | 788464 |
| cumulative_category_provided      | 787174 |
| monthly_date_raw                  |      0 |
| monthly_category_provided         |      0 |
| daily_actual_mm                   |  21772 |
| daily_normal_mm                   |   8868 |
| daily_departure_pct_provided      |  34563 |
| weekly_actual_mm_provided         | 792670 |
| weekly_normal_mm_provided         | 789538 |
| weekly_departure_pct_provided     | 801468 |
| cumulative_actual_mm_provided     | 791658 |
| cumulative_normal_mm_provided     | 789538 |
| cumulative_departure_pct_provided | 799011 |
| monthly_actual_mm_provided        |  13242 |
| monthly_normal_mm_provided        |   8895 |
| monthly_departure_pct_provided    |  23072 |

## Duplicates on (state, district, date)
- Duplicate rows: **88844** (42258 groups)

## Value QC summary
- Negative daily actual: 0
- Zero daily actual: 850002
- Extreme (>500.0 mm): 21
- Daily actual max: 1224.800048828125 mm

## Departure recompute (normal >= {guard} mm)
|                    |             0 |
|:-------------------|--------------:|
| n_comparable       | 525008        |
| median_abs_diff_pp |      0.178215 |
| mean_abs_diff_pp   |      3.05033  |
| pct_within_1pp     |     91.1335   |

## Category agreement (recomputed vs provided): **97.66%**

## Weekly actual vs daily (by date, % equal)
|       |        n |   pct_weekly_eq_daily |
|:------|---------:|----------------------:|
| count | 1800     |             1800      |
| mean  |  733.761 |               22.6364 |
| std   |  107.612 |               36.82   |
| min   |   27     |                0      |
| 25%   |  719     |                0      |
| 50%   |  725     |                0      |
| 75%   |  728     |               37.3443 |
| max   | 4040     |              100      |

## Consistency checks
- Normal stability (same DOY multiple values): {'groups': 267477, 'groups_multiple_normals': 239200, 'pct_unstable': np.float64(89.42824990559936)}
- Cumulative vs daily sum: {'n_checks': 7889, 'pass_rate_pct': 13.702623906705538}
- Monthly vs daily sum: {'n_checks': 48003, 'pass_rate_pct': 35.27071224715122}

## Known issues register
1. Duplicate keys resolved in clean stage (prefer non-null actual; richer obj_id history).
2. Departure % unreliable when normal ≈ 0; recompute with guard.
3. Categories recomputed from guarded departure; provided kept.
4. Weekly columns often equal daily — not rolling 7-day; compute own rolling sums.
5. Obj_Id not a shapefile key; missing ~72% in full data.
6. District/state name variants require crosswalk + aliases.
