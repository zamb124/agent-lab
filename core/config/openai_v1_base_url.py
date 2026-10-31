"""Канонизация корня OpenAI-совместимого API (``…/v1``) и адреса provider_litserve.

Единственный источник адреса сервиса — ``server.provider_litserve_service_url``
(``ServerConfig.get_service_url``): внутри кластера — ClusterIP, локально —
``127.0.0.1:8014``. Все производные (``…/v1``, speech-эндпоинты, ключ /v1)
вычисляются отсюда; отдельные ``*.base_url`` override — только явный побег.
"""

from __future__ import annotations


def normalize_openai_v1_base_url(url: str) -> str:
    """
    Корень OpenAI-совместимого API (как у OpenRouter: ``.../api/v1``).

    Ожидается суффикс ``/v1`` без хвостового слэша (после нормализации).
    """
    u = url.strip().rstrip("/")
    if not u.endswith("/v1"):
        raise ValueError(
            f"provider_litserve: base_url must end with /v1 (OpenAI API root), got: {url!r}"
        )
    return u


def openai_v1_base_url(service_url: str) -> str:
    """OpenAI-совместимый корень сервиса: ``<service_url>/v1``."""
    return normalize_openai_v1_base_url(service_url.strip().rstrip("/") + "/v1")


def provider_litserve_service_url() -> str:
    """Канонический адрес provider_litserve для текущего процесса (без ``/v1``)."""
    from core.config import get_settings

    return get_settings().server.get_service_url("provider_litserve")


def provider_litserve_api_key() -> str | None:
    """Ключ для ``Authorization: Bearer`` на ``/v1`` (``LIT_SERVER_API_KEY`` на поде)."""
    from core.config import get_settings

    key = get_settings().provider_litserve.lit_server_api_key
    if key is None or not key.strip():
        return None
    return key.strip()


PROVIDER_LITSERVE_PLACEHOLDER_BEARER = "local-litserve"


def provider_litserve_sdk_api_key() -> str:
    """Непустой ``api_key`` для AsyncOpenAI-клиентов ``/v1`` provider_litserve.

    OpenAI SDK отклоняет пустой ``api_key``; при выключенном
    ``LIT_SERVER_API_KEY`` сервер Bearer не проверяет — подставляется
    placeholder. httpx-клиенты речи этой формы не требуют: без ключа
    заголовок ``Authorization`` не отправляется вовсе.
    """
    return provider_litserve_api_key() or PROVIDER_LITSERVE_PLACEHOLDER_BEARER
