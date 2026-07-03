"""Redis extract-cache для read_file.

Первый read = полный extract файла кладётся в Redis (TTL 24ч). Повторные read
(другие страницы / summary) — дешёвый render из кэша, без повторного S3 и парсинга.
Cache miss (истёк TTL / первого read не было) → caller перечитывает файл и кладёт
заново. Ошибки Redis не фатальны: кэш просто пропускается (см. RedisClient.get/set).
"""

from __future__ import annotations

from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.files.reader.models import FileExtract
from core.logging import get_logger

logger = get_logger(__name__)

_EXTRACT_CACHE_TTL_SECONDS: int = 24 * 60 * 60
_KEY_PREFIX: str = "file_extract"

_redis_client: RedisClient | None = None


def _client() -> RedisClient:
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient(get_settings().database.redis_url)
    return _redis_client


def extract_cache_key(*, file_id: str | None, checksum: str | None) -> str | None:
    if file_id is not None and file_id.strip():
        return f"{_KEY_PREFIX}:{file_id.strip()}"
    if checksum is not None and checksum.strip():
        return f"{_KEY_PREFIX}:sha:{checksum.strip()}"
    return None


async def load_file_extract(*, file_id: str | None, checksum: str | None) -> FileExtract | None:
    key = extract_cache_key(file_id=file_id, checksum=checksum)
    if key is None:
        return None
    raw = await _client().get(key)
    if raw is None:
        return None
    try:
        return FileExtract.model_validate_json(raw)
    except ValueError as exc:
        logger.warning("extract_cache: повреждённая запись %s: %s", key, exc)
        return None


async def store_file_extract(extract: FileExtract) -> None:
    key = extract_cache_key(file_id=extract.file_id, checksum=extract.source_checksum)
    if key is None:
        return
    stored = await _client().set(key, extract.model_dump_json(), ttl=_EXTRACT_CACHE_TTL_SECONDS)
    if not stored:
        logger.warning("extract_cache: не удалось записать %s (Redis недоступен) — продолжаем", key)


def _vision_page_key(*, file_id: str | None, checksum: str | None, page: int) -> str | None:
    base = extract_cache_key(file_id=file_id, checksum=checksum)
    if base is None:
        return None
    return f"{base}:vis:{page}"


async def load_vision_page(
    *, file_id: str | None, checksum: str | None, page: int
) -> str | None:
    """Кэш одной обработанной vision-страницы (ленивый режим без пере-биллинга)."""
    key = _vision_page_key(file_id=file_id, checksum=checksum, page=page)
    if key is None:
        return None
    return await _client().get(key)


async def store_vision_page(
    *, file_id: str | None, checksum: str | None, page: int, text: str
) -> None:
    key = _vision_page_key(file_id=file_id, checksum=checksum, page=page)
    if key is None:
        return
    _ = await _client().set(key, text, ttl=_EXTRACT_CACHE_TTL_SECONDS)
