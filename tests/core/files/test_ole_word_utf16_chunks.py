"""UTF-16 LE куски WordDocument stream читаются без перехвата ошибок."""

from core.files.reader.service import _utf16_le_readable_chunks


def test_utf16_le_readable_chunks_finds_text() -> None:
    stream = "Hello".encode("utf-16-le")
    assert _utf16_le_readable_chunks(stream) == ["Hello"]


def test_utf16_le_readable_chunks_ignores_odd_trailing_byte() -> None:
    stream = "Hello".encode("utf-16-le") + b"\xff"
    assert _utf16_le_readable_chunks(stream) == ["Hello"]
