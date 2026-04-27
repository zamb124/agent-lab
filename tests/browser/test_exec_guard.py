"""Ограничения exec_code."""

import pytest

from apps.browser.engine.playwright_interactor import _assert_no_imports


def test_exec_rejects_import() -> None:
    with pytest.raises(ValueError, match="import"):
        _assert_no_imports("import os\nx = 1")


def test_exec_rejects_from_import() -> None:
    with pytest.raises(ValueError, match="import"):
        _assert_no_imports("from pathlib import Path")


def test_exec_allows_expression_only() -> None:
    _assert_no_imports("x = 1 + 2")
