"""Slug из произвольного текста: транслитерация кириллицы, lowercase, `[a-z0-9-]`."""

import hashlib
import re

TRANSLIT_MAP = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "А": "A",
    "Б": "B",
    "В": "V",
    "Г": "G",
    "Д": "D",
    "Е": "E",
    "Ё": "Yo",
    "Ж": "Zh",
    "З": "Z",
    "И": "I",
    "Й": "Y",
    "К": "K",
    "Л": "L",
    "М": "M",
    "Н": "N",
    "О": "O",
    "П": "P",
    "Р": "R",
    "С": "S",
    "Т": "T",
    "У": "U",
    "Ф": "F",
    "Х": "H",
    "Ц": "Ts",
    "Ч": "Ch",
    "Ш": "Sh",
    "Щ": "Sch",
    "Ъ": "",
    "Ы": "Y",
    "Ь": "",
    "Э": "E",
    "Ю": "Yu",
    "Я": "Ya",
}

_HASH_SUFFIX_LENGTH = 6


def transliterate(text: str) -> str:
    return "".join(TRANSLIT_MAP.get(char, char) for char in text)


def slugify(text: str, *, max_length: int = 63, hash_suffix: bool = False) -> str:
    """Slug без краевых и двойных дефисов; пустая строка, если в тексте нет `[a-z0-9]`.

    `hash_suffix` добавляет детерминированный md5-хвост исходного текста — для имён
    во внешних системах, где одно и то же название должно давать один и тот же slug.
    """
    slug = transliterate(text).lower()
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if hash_suffix:
        digest = hashlib.md5(text.encode()).hexdigest()[:_HASH_SUFFIX_LENGTH]
        base = slug[: max_length - _HASH_SUFFIX_LENGTH - 1].rstrip("-")
        return f"{base}-{digest}" if base else digest
    return slug[:max_length].rstrip("-")
