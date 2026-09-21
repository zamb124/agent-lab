"""Канонизация корня OpenAI-совместимого API (``…/v1``) без зависимости от ``core.rag``."""


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
