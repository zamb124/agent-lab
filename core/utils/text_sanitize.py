"""Нормализация текста для обмена с внешними UTF-8/FFI (TTS, токенайзеры)."""

from __future__ import annotations

import unicodedata


def sanitize_text_for_speech_backend(text: str) -> str:
    """Приводит текст к безопасному для FFI бэкендов речи UTF-8 (в т.ч. Silero, облачные API).

    Порядок: NFKC, замена lone surrogate, удаление Cc (кроме \\n/\\r/\\t),
    удаление категории Cf (форматные: ZWSP, ZWJ, BOM и т.п. — часто ломают
    espeak/phonemizer), контроль что результат кодируется в UTF-8.
    Пустая строка на входе — пустая на выходе; проверку «обязательного текста»
    выполняет вызывающий код.
    """
    if text == "":
        return ""

    t = unicodedata.normalize("NFKC", text)
    t = t.encode("utf-16", "surrogatepass").decode("utf-16", "replace")

    allowed_cc = "\n\r\t"
    out: list[str] = []
    for ch in t:
        cat = unicodedata.category(ch)
        if cat == "Cc" and ch not in allowed_cc:
            continue
        if cat == "Cf":
            continue
        out.append(ch)
    t = "".join(out)

    _ = t.encode("utf-8")
    return t.strip()
