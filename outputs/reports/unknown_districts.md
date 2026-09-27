# Unknown Districts Of India

Total rows: **5,774**

## By state
| state                       |   n_rows |   n_days |   n_null_actual |   mean_actual | obj_ids                        |
|:----------------------------|---------:|---------:|----------------:|--------------:|:-------------------------------|
| Andaman and Nicobar Islands |     2718 |     1084 |               1 |      11.242   | []                             |
| Chhattisgarh                |     2333 |      703 |               0 |       7.44518 | [176, 185, 235, 308, 592, 811] |
| Maharashtra                 |      723 |      703 |               1 |      10.0838  | [157]                          |

## By year (row count)
|   date |   n_rows |
|-------:|---------:|
|   2021 |      927 |
|   2022 |      898 |
|   2023 |      893 |
|   2024 |     1520 |
|   2025 |      942 |
|   2026 |      594 |

## Values
- Rows with NaN daily actual: **2**
- Rows with non-NaN actual: **5772**

## Obj_Id notes
Obj_Id 235 and 811 appear under Raigarh (Chhattisgarh) in named districts; Unknown rows share overlapping Obj_Id patterns.

### Obj_Id → IMD name (where id exists in gist)
|   obj_id | imd_name            | imd_state    |   n_rows |
|---------:|:--------------------|:-------------|---------:|
|      235 | RAIGARH             | CHHATTISGARH |      722 |
|      811 | nan                 | nan          |      579 |
|      157 | SUB URBAN MUMBAI    | MAHARASHTRA  |      723 |
|      176 | UTTAR BASTAR KANKER | CHHATTISGARH |      258 |
|      185 | DHAMTARI            | CHHATTISGARH |      258 |
|      308 | SURAJPUR            | CHHATTISGARH |      258 |
|      592 | NARAINPUR           | CHHATTISGARH |      258 |

## Decision
Unknown rows with mappable Obj_Id to a **single** IMD district will be **relabeled** in M3 (`qc_relabelled_unknown`). Remaining Unknown rows stay excluded with `qc_placeholder_district`.
