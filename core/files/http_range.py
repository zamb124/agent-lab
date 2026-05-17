"""
Разбор заголовка Range для отдачи файлов из S3.

Safari (в т.ч. iOS) для <audio> часто запрашивает фрагменты байтов; без корректного
ответа 206 и Accept-Ranges воспроизведение может завершаться NotSupportedError.
"""

from __future__ import annotations


class RangeNotSatisfiableError(Exception):
    def __init__(self, total_size: int) -> None:
        super().__init__(f"Range not satisfiable for object size {total_size}")
        self.total_size = total_size


def normalize_s3_byte_range(range_header: str | None, total: int) -> tuple[int, int] | None:
    """
    Возвращает пару (start, end) включительно для одного интервала bytes=...,
    либо None — отдавать весь объект (200).

    Некорректный синтаксис Range игнорируем (полный ответ), как допускает RFC 7233.
    Невыполнимый диапазон — RangeNotSatisfiableError.
    """
    if total < 0:
        raise ValueError("total must be non-negative")
    if total == 0:
        if range_header and range_header.strip():
            raise RangeNotSatisfiableError(0)
        return None
    if not range_header:
        return None
    raw = range_header.strip()
    lower = raw.lower()
    if not lower.startswith("bytes="):
        return None
    spec = raw[6:].strip()
    first = spec.split(",", 1)[0].strip()
    if "-" not in first:
        return None
    left, right = first.split("-", 1)
    try:
        if left == "":
            if right == "":
                return None
            suffix_len = int(right)
            if suffix_len <= 0:
                return None
            if suffix_len >= total:
                return 0, total - 1
            start = total - suffix_len
            return start, total - 1
        start = int(left)
        if right == "":
            end = total - 1
        else:
            end = int(right)
    except ValueError:
        return None
    if start < 0:
        return None
    if start >= total:
        raise RangeNotSatisfiableError(total)
    end = min(end, total - 1)
    if start > end:
        raise RangeNotSatisfiableError(total)
    return start, end
