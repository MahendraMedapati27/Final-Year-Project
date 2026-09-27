"""NumPy matrix hydrology: paint_group x calendar days."""

from __future__ import annotations

import numpy as np
import pandas as pd

CAL_START = pd.Timestamp("2021-01-01")
CAL_END = pd.Timestamp("2026-09-19")


def calendar_index() -> pd.DatetimeIndex:
    return pd.date_range(CAL_START, CAL_END, freq="D")


def build_paint_group_matrix(
    df: pd.DataFrame,
    paint_to_idx: dict[int, int],
    dates: pd.DatetimeIndex,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return actual, normal float32 [n_pg, n_days], and present mask bool."""
    n_pg = len(paint_to_idx)
    n_d = len(dates)
    date_to_i = {d: i for i, d in enumerate(dates)}
    actual = np.full((n_pg, n_d), np.nan, dtype=np.float32)
    normal = np.full((n_pg, n_d), np.nan, dtype=np.float32)
    present = np.zeros((n_pg, n_d), dtype=np.bool_)

    sub = df.dropna(subset=["paint_group_uid", "date"]).copy()
    sub = sub[sub["paint_group_uid"] > 0]
    sub["paint_group_uid"] = sub["paint_group_uid"].astype(int)
    sub["date"] = pd.to_datetime(sub["date"])
    sub = sub[(sub["date"] >= dates.min()) & (sub["date"] <= dates.max())]
    sub["di"] = sub["date"].map(date_to_i)
    sub["pi"] = sub["paint_group_uid"].map(paint_to_idx)
    sub = sub.dropna(subset=["di", "pi"])
    sub["pi"] = sub["pi"].astype(int)
    sub["di"] = sub["di"].astype(int)
    val_col = "daily_actual_mm_map" if "daily_actual_mm_map" in sub.columns else "daily_actual_mm"
    for col, arr in ((val_col, actual), ("daily_normal_mm", normal)):
        v = sub.groupby(["pi", "di"], observed=True)[col].first()
        for (pi, di), val in v.items():
            arr[int(pi), int(di)] = np.float32(val) if pd.notna(val) else np.nan
    for pi, di in zip(sub["pi"], sub["di"]):
        present[int(pi), int(di)] = True

    return actual, normal, present


def rolling_sum_nan_strict(arr: np.ndarray, present: np.ndarray, window: int) -> np.ndarray:
    """Sum over window; NaN if any day in window missing or any actual NaN in window."""
    n_pg, n_d = arr.shape
    out = np.full_like(arr, np.nan, dtype=np.float32)
    for w in range(window - 1, n_d):
        sl = slice(w - window + 1, w + 1)
        block = arr[:, sl]
        pres = present[:, sl]
        if window == 1:
            ok = pres
        else:
            ok = pres.all(axis=1)
        with np.errstate(invalid="ignore"):
            sums = np.nansum(block, axis=1)
        sums[~ok] = np.nan
        out[:, w] = sums.astype(np.float32)
    return out


def monsoon_cumulative(actual: np.ndarray, present: np.ndarray, dates: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """Cumsum since June 1 each year; NaN if any missing day from Jun 1 through current day."""
    n_pg, n_d = actual.shape
    out = np.full_like(actual, np.nan, dtype=np.float32)
    complete = np.zeros((n_pg, n_d), dtype=np.bool_)
    years = dates.year.values
    months = dates.month.values
    for pi in range(n_pg):
        for di in range(n_d):
            if not present[pi, di]:
                continue
            y = years[di]
            if months[di] < 6:
                continue
            j0 = np.where((years == y) & (months >= 6) & (np.arange(n_d) <= di))[0]
            if len(j0) == 0:
                continue
            start = j0[0]
            seg_p = present[pi, start : di + 1]
            if not seg_p.all():
                continue
            complete[pi, di] = True
            out[pi, di] = np.nansum(actual[pi, start : di + 1])
    return out, complete


def spells_and_since_rain(actual: np.ndarray, present: np.ndarray, rainy_thresh: float = 2.5) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_pg, n_d = actual.shape
    dry = np.zeros((n_pg, n_d), dtype=np.int16)
    wet = np.zeros((n_pg, n_d), dtype=np.int16)
    dsr = np.full((n_pg, n_d), -1, dtype=np.int16)
    for pi in range(n_pg):
        run_d = run_w = 0
        since = -1
        for di in range(n_d):
            if not present[pi, di] or np.isnan(actual[pi, di]):
                dry[pi, di] = wet[pi, di] = -1
                dsr[pi, di] = -1
                run_d = run_w = 0
                since = -1
                continue
            is_r = actual[pi, di] >= rainy_thresh
            if is_r:
                run_w += 1
                run_d = 0
                since = 0
            else:
                run_d += 1
                run_w = 0
                if since >= 0:
                    since += 1
            dry[pi, di] = run_d
            wet[pi, di] = run_w
            dsr[pi, di] = since
    return dry, wet, dsr


def melt_features(
    df: pd.DataFrame,
    paint_to_idx: dict[int, int],
    idx_to_paint: dict[int, int],
    dates: pd.DatetimeIndex,
    mats: dict[str, np.ndarray],
) -> pd.DataFrame:
    """Attach matrix columns back to long df on (paint_group_uid, date)."""
    date_to_i = {d: i for i, d in enumerate(dates)}
    for name, mat in mats.items():
        df[name] = np.nan
    for idx, row in df.iterrows():
        pg = row.get("paint_group_uid")
        if pd.isna(pg) or int(pg) <= 0:
            continue
        pg = int(pg)
        if pg not in paint_to_idx:
            continue
        pi = paint_to_idx[pg]
        di = date_to_i.get(pd.Timestamp(row["date"]))
        if di is None:
            continue
        for name, mat in mats.items():
            val = mat[pi, di]
            if isinstance(val, (bool, np.bool_)):
                df.at[idx, name] = bool(val)
            elif val == -1 and name.endswith("_len"):
                df.at[idx, name] = np.nan
            else:
                df.at[idx, name] = float(val) if not isinstance(val, (bool, np.bool_)) else val
    return df
