"""Unit tests for DoclingParser table-row conversion.

Exercises _dataframe_to_rows without loading Docling models — fast, no I/O.
"""
from __future__ import annotations

import pandas as pd
import pytest

from application.dtos.parsed_document import Block
from infrastructure.file_services.docling_parser import _dataframe_to_rows


def _make_df_integer_columns() -> pd.DataFrame:
    """DataFrame with default RangeIndex (integer) columns — the failing case."""
    return pd.DataFrame([["GSK286", "5"], ["GSK123", "12"]])


def _make_df_named_columns() -> pd.DataFrame:
    return pd.DataFrame([["GSK286", "5"], ["GSK123", "12"]], columns=["compound", "ic50"])


def test_all_cells_are_strings_with_integer_columns():
    df = _make_df_integer_columns()
    rows = _dataframe_to_rows(df)
    for row in rows:
        for cell in row:
            assert isinstance(cell, str), f"Expected str, got {type(cell)!r}: {cell!r}"


def test_header_row_is_stringified():
    df = _make_df_integer_columns()
    rows = _dataframe_to_rows(df)
    assert rows[0] == ["0", "1"], f"Header row wrong: {rows[0]}"


def test_body_rows_correct():
    df = _make_df_integer_columns()
    rows = _dataframe_to_rows(df)
    assert rows[1] == ["GSK286", "5"]
    assert rows[2] == ["GSK123", "12"]


def test_named_columns_still_work():
    df = _make_df_named_columns()
    rows = _dataframe_to_rows(df)
    assert rows[0] == ["compound", "ic50"]
    assert rows[1] == ["GSK286", "5"]


def test_block_construction_succeeds_with_integer_columns():
    """Block(type='table', rows=...) must not raise ValidationError."""
    df = _make_df_integer_columns()
    rows = _dataframe_to_rows(df)
    block = Block(type="table", rows=rows)
    assert block.rows is not None
    assert len(block.rows) == 3  # header + 2 body rows
