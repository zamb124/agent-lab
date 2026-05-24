"""
Контракт времени жизни документов RAG для индексации и TTL-очистки.

`ttl_seconds` в metadata документа: время жизни в секундах от момента готовности
индекса (`completed_at` для пайплайна со статусом; `min(chunk.created_at)`
для чанков без строки статуса). Значение `0` означает бессрочное хранение.
Если ключ `ttl_seconds` в metadata не указан при загрузке, подставляется
`rag.ttl.default_ttl_seconds` из конфигурации.

Валидация входа: ключ опционален; если присутствует, допустимо только целое
неотрицательное число.
"""

from collections.abc import Mapping

from core.types import JsonObject, JsonValue


def resolve_document_ttl_seconds(
    *,
    ttl_raw: JsonValue | None,
    default_ttl_seconds: int,
) -> int:
    """
    Возвращает канонический ttl_seconds для документа.

    ``ttl_raw`` — значение опционального ключа из metadata клиента или None при отсутствии ключа.
    ``default_ttl_seconds`` — всегда > 0 (из ``rag.ttl.default_ttl_seconds``).
    Результат: ``0`` (бессрочно) или положительное целое.
    """
    if default_ttl_seconds < 1:
        raise ValueError("default_ttl_seconds должен быть >= 1")
    if ttl_raw is None:
        return int(default_ttl_seconds)
    if isinstance(ttl_raw, bool):
        raise ValueError("ttl_seconds не может быть булевым")
    if isinstance(ttl_raw, int):
        if ttl_raw < 0:
            raise ValueError("ttl_seconds не может быть отрицательным")
        return int(ttl_raw)
    if isinstance(ttl_raw, float):
        if not ttl_raw.is_integer():
            raise ValueError("ttl_seconds должен быть целым числом секунд")
        v = int(ttl_raw)
        if v < 0:
            raise ValueError("ttl_seconds не может быть отрицательным")
        return v
    if isinstance(ttl_raw, str):
        s = ttl_raw.strip()
        if not s:
            raise ValueError("ttl_seconds пустая строка")
        parsed = int(s, 10)
        if parsed < 0:
            raise ValueError("ttl_seconds не может быть отрицательным")
        return parsed
    raise ValueError("ttl_seconds должен быть целым неотрицательным числом")


def ensure_ttl_seconds_in_metadata(
    metadata: Mapping[str, JsonValue],
    *,
    default_ttl_seconds: int,
) -> JsonObject:
    """
    Копия metadata с гарантированным ключом ``ttl_seconds`` (каноничное число).

    Если ключа не было — подставляет ``default_ttl_seconds``.
    """
    md = dict(metadata)
    ttl_key = md.get("ttl_seconds", None)
    md["ttl_seconds"] = resolve_document_ttl_seconds(
        ttl_raw=ttl_key,
        default_ttl_seconds=default_ttl_seconds,
    )
    return md
