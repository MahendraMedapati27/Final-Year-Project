"""Tests for CSV header mapping and ingest."""

from pathlib import Path

import pytest

from rainfall.config import project_root, raw_csv_path, load_config
from rainfall.io import EXPECTED_N_COLS, ingest_raw_csv, map_raw_columns, read_raw_header


@pytest.fixture
def sample_csv() -> Path:
    return raw_csv_path(load_config(), sample=True)


def test_header_has_25_columns(sample_csv: Path) -> None:
    cols = read_raw_header(sample_csv)
    assert len(cols) == EXPECTED_N_COLS


def test_column_mapping(sample_csv: Path) -> None:
    cols = read_raw_header(sample_csv)
    mapping = map_raw_columns(cols)
    assert mapping[cols[0]] == "country"
    assert mapping[cols[13]] == "daily_actual_mm"
    assert "monthly_actual_mm_provided" in mapping.values()


def test_ingest_sample_row_count(sample_csv: Path) -> None:
    df = ingest_raw_csv(sample_csv)
    assert len(df) == 5000
    assert "date" in df.columns
    assert df["daily_actual_mm"].dtype.name == "float32"
