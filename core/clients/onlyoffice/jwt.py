"""
Каноничный sign/verify HS256-JWT для OnlyOffice Document Server.

Назначение
----------
Единственное место в платформе, где исполняется криптография JWT для
OnlyOffice. Раньше `jwt.encode`/`jwt.decode` дублировались в трёх местах
сервиса `apps/office` (`services/onlyoffice_jwt.py`,
`services/callback_token.py`, `api/bff.py`), что нарушало DRY и плодило
риск рассинхрона алгоритма/секрета.

Контракт
--------
- Алгоритм: HS256.
- Секрет: непустая строка; пустая — `OnlyOfficeJwtError` сразу, без try.
- Возврат `verify_*`: `JsonObject` (claim-нормализация — на стороне
  доменных моделей в `apps/office/services/**`).
- На ошибку верификации — `OnlyOfficeJwtError` (обёртка над
  `jwt.InvalidTokenError`), чтобы вызывающий слой обрабатывал её
  единообразно, без зависимости от `pyjwt`-исключений.
"""

from __future__ import annotations

import jwt

from core.types import JsonObject, require_json_object


class OnlyOfficeJwtError(Exception):
    """Ошибка подписи или верификации OnlyOffice JWT."""


def sign_onlyoffice_jwt_hs256(payload: JsonObject, secret: str) -> str:
    if not secret.strip():
        raise OnlyOfficeJwtError("secret пуст")
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_onlyoffice_jwt_hs256(token: str, secret: str) -> JsonObject:
    if not secret.strip():
        raise OnlyOfficeJwtError("secret пуст")
    try:
        decoded = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise OnlyOfficeJwtError(str(exc)) from exc
    return require_json_object(decoded, "OnlyOffice JWT payload")
