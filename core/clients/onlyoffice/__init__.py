"""
Платформенные клиенты/утилиты OnlyOffice.

Низкоуровневая криптография (HS256-подпись/верификация JWT) живёт здесь, чтобы
не разводить три копии `jwt.encode/decode` по `apps/office/**`. Высокоуровневые
обёртки с конкретными claim-моделями (например, `OnlyOfficeDownloadTokenClaims`,
`OnlyOfficeCallbackContextClaims`) остаются в `apps/office/services/**` и
используют этот модуль как единственную точку подписи/верификации.
"""

from core.clients.onlyoffice.jwt import (
    OnlyOfficeJwtError,
    sign_onlyoffice_jwt_hs256,
    verify_onlyoffice_jwt_hs256,
)

__all__ = [
    "OnlyOfficeJwtError",
    "sign_onlyoffice_jwt_hs256",
    "verify_onlyoffice_jwt_hs256",
]
