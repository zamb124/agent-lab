"""ReadFileArgs accepts LLM wire quirks for names (JSON-stringified array)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.files.reader.models import ReadFileArgs


def test_read_file_args_names_list() -> None:
    args = ReadFileArgs.model_validate({"names": ["IMG_2444.JPG"]})
    assert args.names == ["IMG_2444.JPG"]


def test_read_file_args_names_json_string_array() -> None:
    args = ReadFileArgs.model_validate({"names": '["IMG_2444.JPG"]'})
    assert args.names == ["IMG_2444.JPG"]


def test_read_file_args_names_plain_filename_string() -> None:
    args = ReadFileArgs.model_validate({"names": "IMG_2444.JPG"})
    assert args.names == ["IMG_2444.JPG"]


def test_read_file_args_names_invalid_json_array_raises() -> None:
    with pytest.raises(ValidationError):
        _ = ReadFileArgs.model_validate({"names": "[not-json"})
