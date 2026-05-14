"""
Шифрование секретов company AI providers (Fernet).

Ключ детерминированно выводится из ``settings.auth.secret_key`` через SHA256 → urlsafe-b64.
Если ``auth.secret_key`` не задан — функции шифрования падают с ValueError (Zero-Guess).

Никаких "пропустим шифрование если ключа нет" — секрет компании не должен сохраняться в БД
в открытом виде.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from core.config import get_settings

_SECRET_MASK_VISIBLE_TAIL = 4


def _derive_fernet_key() -> bytes:
    """Стабильно выводит 32-байтовый Fernet-ключ из ``auth.jwt_secret_key`` или ``auth.secret_key``.

    Любой непустой источник годится: пере-выпуск секрета приведёт к невозможности расшифровать
    старые токены — это намеренно (миграционный сценарий — отдельный тулинг).
    """
    settings = get_settings()
    candidates = (
        getattr(settings.auth, "jwt_secret_key", None),
        getattr(settings.auth, "secret_key", None),
    )
    for raw in candidates:
        if raw is not None and str(raw).strip():
            digest = hashlib.sha256(str(raw).strip().encode("utf-8")).digest()
            return base64.urlsafe_b64encode(digest)
    raise ValueError(
        "core.company_ai.crypto: ни auth.jwt_secret_key, ни auth.secret_key не заданы; "
        "без секрета нельзя шифровать секреты company AI providers"
    )


def _fernet() -> Fernet:
    return Fernet(_derive_fernet_key())


def encrypt_secret(plaintext: str) -> str:
    """Шифрует секрет в base64-токен Fernet. Пустую строку считаем ошибкой."""
    if not isinstance(plaintext, str):
        raise TypeError("encrypt_secret: plaintext должен быть str")
    if not plaintext.strip():
        raise ValueError("encrypt_secret: plaintext пуст")
    token = _fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_secret(token: str) -> str:
    """Расшифровывает Fernet-токен; невалидный/чужой ключ → ValueError."""
    if not isinstance(token, str) or not token.strip():
        raise ValueError("decrypt_secret: token пуст")
    try:
        plain = _fernet().decrypt(token.encode("ascii"))
    except InvalidToken as e:
        raise ValueError(
            "decrypt_secret: невалидный Fernet-токен (или несовпадающий auth.secret_key)"
        ) from e
    return plain.decode("utf-8")


def mask_secret_plaintext(plaintext: Optional[str]) -> str:
    """Возвращает '**** abcd' (последние 4 символа). Для None/пусто — '****'."""
    if plaintext is None or not str(plaintext).strip():
        return "****"
    s = str(plaintext)
    tail = s[-_SECRET_MASK_VISIBLE_TAIL:] if len(s) >= _SECRET_MASK_VISIBLE_TAIL else s
    return f"**** {tail}"


def mask_encrypted_secret(token: Optional[str]) -> str:
    """Расшифровывает и маскирует — для GET ответов API. Token=None → '****'."""
    if token is None or not str(token).strip():
        return "****"
    return mask_secret_plaintext(decrypt_secret(token))


__all__ = [
    "decrypt_secret",
    "encrypt_secret",
    "mask_encrypted_secret",
    "mask_secret_plaintext",
]
