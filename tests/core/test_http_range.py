"""Тесты разбора HTTP Range для S3-скачивания."""

import pytest

from core.files.http_range import RangeNotSatisfiableError, normalize_s3_byte_range


def test_no_header_means_full() -> None:
    assert normalize_s3_byte_range(None, 100) is None
    assert normalize_s3_byte_range("", 100) is None
    assert normalize_s3_byte_range("   ", 100) is None


def test_prefix_range() -> None:
    assert normalize_s3_byte_range("bytes=0-4", 10) == (0, 4)
    assert normalize_s3_byte_range("bytes=5-9", 10) == (5, 9)


def test_open_ended_range() -> None:
    assert normalize_s3_byte_range("bytes=3-", 10) == (3, 9)


def test_suffix_range() -> None:
    assert normalize_s3_byte_range("bytes=-3", 10) == (7, 9)
    assert normalize_s3_byte_range("bytes=-100", 10) == (0, 9)


def test_clamp_end_to_size() -> None:
    assert normalize_s3_byte_range("bytes=0-999", 5) == (0, 4)


def test_invalid_syntax_ignored() -> None:
    assert normalize_s3_byte_range("bytes=", 10) is None
    assert normalize_s3_byte_range("bytes=abc", 10) is None
    assert normalize_s3_byte_range("units=0-1", 10) is None


def test_unsatisfiable_start() -> None:
    with pytest.raises(RangeNotSatisfiableError) as exc_info:
        normalize_s3_byte_range("bytes=10-11", 10)
    assert exc_info.value.total_size == 10


def test_zero_length_object_with_range() -> None:
    with pytest.raises(RangeNotSatisfiableError):
        normalize_s3_byte_range("bytes=0-0", 0)


def test_first_range_only_if_comma() -> None:
    assert normalize_s3_byte_range("bytes=0-1, 4-5", 10) == (0, 1)
