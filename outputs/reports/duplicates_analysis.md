# Duplicate key analysis `(state, district, date)`

- Duplicate **groups**: 42,258 · duplicate **rows**: 88,844

## By calendar year (duplicate rows / groups)
|   year |   n_dup_rows |   n_groups |
|-------:|-------------:|-----------:|
|   2021 |        18297 |       9035 |
|   2022 |        18087 |       8943 |
|   2023 |        18036 |       8924 |
|   2024 |        18406 |       7415 |
|   2025 |        11464 |       5671 |
|   2026 |         4554 |       2270 |

## Top states by duplicate row count
| state                                        |   dup_rows |
|:---------------------------------------------|-----------:|
| Jammu and Kashmir                            |      44187 |
| Andaman and Nicobar Islands                  |       9269 |
| Chhattisgarh                                 |       4694 |
| Uttar Pradesh                                |       3018 |
| Karnataka                                    |       2885 |
| Madhya Pradesh                               |       2120 |
| Telangana                                    |       1933 |
| Bihar                                        |       1673 |
| Tamil Nadu                                   |       1628 |
| Maharashtra                                  |       1462 |
| Gujarat                                      |       1360 |
| Rajasthan                                    |       1353 |
| Odisha                                       |       1328 |
| The Dadra and Nagar Haveli and Daman and Diu |       1133 |
| Assam                                        |       1118 |

## Obj_Id null pattern (within duplicate groups)
|                  |   count |
|:-----------------|--------:|
| both_obj_null    |   26902 |
| mixed_obj_null   |       0 |
| neither_obj_null |   15356 |

## Pairwise pattern (groups with exactly 2 rows)
|                    |   groups |
|:-------------------|---------:|
| identical_values   |    37682 |
| diff_values        |     2828 |
| one_all_nan_actual |     4564 |
| diff_obj_id        |     1570 |

## Top 30 districts by duplicate days
| state                                        | district                   |   n_duplicate_days |
|:---------------------------------------------|:---------------------------|-------------------:|
| Andaman and Nicobar Islands                  | Unknown Districts Of India |               1326 |
| Chhattisgarh                                 | Unknown Districts Of India |               1166 |
| Jammu and Kashmir                            | Reasi                      |               1105 |
| Jammu and Kashmir                            | Shopian                    |               1105 |
| Jammu and Kashmir                            | Udhampur                   |               1105 |
| Jammu and Kashmir                            | Budgam                     |               1105 |
| Jammu and Kashmir                            | Anantnag                   |               1105 |
| Jammu and Kashmir                            | Kupwara                    |               1105 |
| Jammu and Kashmir                            | Srinagar                   |               1105 |
| Jammu and Kashmir                            | Rajouri                    |               1105 |
| Jammu and Kashmir                            | Ramban                     |               1105 |
| Jammu and Kashmir                            | Baramulla                  |               1105 |
| Jammu and Kashmir                            | Ganderbal                  |               1105 |
| Jammu and Kashmir                            | Kulgam                     |               1105 |
| Jammu and Kashmir                            | Poonch                     |               1105 |
| Jammu and Kashmir                            | Doda                       |               1104 |
| Jammu and Kashmir                            | Pulwama                    |               1104 |
| Jammu and Kashmir                            | Jammu                      |               1104 |
| Jammu and Kashmir                            | Bandipora                  |               1104 |
| Andaman and Nicobar Islands                  | South Andamans             |               1103 |
| Jammu and Kashmir                            | Kishtwar                   |               1103 |
| Jammu and Kashmir                            | Kathua                     |               1103 |
| Andaman and Nicobar Islands                  | North and Middle Andaman   |               1103 |
| Jammu and Kashmir                            | Samba                      |               1103 |
| Andaman and Nicobar Islands                  | Nicobars                   |               1102 |
| Karnataka                                    | Vijayapura                 |                807 |
| Chhattisgarh                                 | Raigarh                    |                596 |
| The Dadra and Nagar Haveli and Daman and Diu | Dadra and Nagar Haveli     |                527 |
| Telangana                                    | Warangal                   |                255 |
| Tamil Nadu                                   | Salem                      |                 23 |

## Obj_Id pairs (sample)
| state        | district                   | obj_ids           |
|:-------------|:---------------------------|:------------------|
| Chhattisgarh | Raigarh                    | 235 vs 811        |
| Chhattisgarh | Unknown Districts Of India | 176 vs 185 vs 235 |
| Karnataka    | Vijayapura                 | 119 vs 807        |

## Obj_Id timeline (replacement vs parallel)
| state        | district                   | obj_ids                      | relationship   |
|:-------------|:---------------------------|:-----------------------------|:---------------|
| Chhattisgarh | Raigarh                    | 235, 811                     | parallel       |
| Chhattisgarh | Unknown Districts Of India | 176, 185, 235, 308, 592, 811 | parallel       |
| Karnataka    | Vijayapura                 | 119, 807                     | parallel       |

## Proposed dedupe rule (implement in M3)
**Proposed M3 rule:** For each `(state, district, date)` group, keep one row: (1) drop rows with NaN `daily_actual_mm` if another row has a value; (2) among ties, prefer the row with non-null `obj_id`; (3) among ties, prefer the `obj_id` whose `(state, district, obj_id)` span covers the row's date and has the latest `last_date` in the full series (current ID); (4) if still tied, prefer larger `daily_actual_mm` (conservative for flood reporting). Log all resolutions to `outputs/tables/duplicates_resolved.csv`.
