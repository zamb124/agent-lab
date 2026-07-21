"""Unit tests for Google Sheets models and cell normalization."""

import pytest
from pydantic import ValidationError

from core.clients.google_sheets_models import (
    ValueInputOption,
    ValueRangeWrite,
    normalize_sheet_cell,
    normalize_sheet_rows_for_write,
    parse_sheet_rows,
)


def test_normalize_int_to_float():
    assert normalize_sheet_cell(3) == 3.0


def test_normalize_none_skip():
    assert normalize_sheet_cell(None) is None


def test_normalize_rows_preserve_none_columns():
    rows = normalize_sheet_rows_for_write([["a", None, 1]])
    assert rows == [["a", None, 1.0]]


def test_parse_sheet_rows_empty():
    assert parse_sheet_rows(None) == []
    assert parse_sheet_rows([]) == []


def test_value_range_write_rejects_blank_range():
    with pytest.raises(ValidationError):
        ValueRangeWrite(range_a1="   ", values=[["x"]])


def test_value_input_option_values():
    assert ValueInputOption.USER_ENTERED.value == "USER_ENTERED"
    assert ValueInputOption.RAW.value == "RAW"
