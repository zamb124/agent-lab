"""
Шифрование значений секретных переменных (Fernet).

Ключ берётся ТОЛЬКО из выделенного ``settings.secrets.encryption_key`` (ENV
``SECRETS__ENCRYPTION_KEY``) — отдельно от ``auth.jwt_secret_key``, чтобы ротация
JWT не ломала расшифровку секретов. Zero-Guess: без ключа шифрование/расшифровка
падают с ValueError — секрет не сохраняется в открытом виде.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from core.config import get_settings

_SECRET_MASK_VISIBLE_TAIL = 4


def _derive_fernet_key() -> bytes:
    """Стабильно выводит 32-байтовый Fernet-ключ из ``settings.secrets.encryption_key``."""
    raw = get_settings().secrets.encryption_key
    if raw is None or not raw.strip():
        raise ValueError(
            "core.secrets.crypto: secrets.encryption_key не задан; без ключа нельзя шифровать секреты"
        )
    digest = hashlib.sha256(raw.strip().encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_derive_fernet_key())


def encrypt_secret(plaintext: str) -> str:
    """Шифрует секрет в base64-токен Fernet. Пустую строку считаем ошибкой."""
    if not plaintext.strip():
        raise ValueError("encrypt_secret: plaintext пуст")
    token = _fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_secret(token: str) -> str:
    """Расшифровывает Fernet-токен; невалидный/чужой ключ → ValueError."""
    if not token.strip():
        raise ValueError("decrypt_secret: token пуст")
    try:
        plain = _fernet().decrypt(token.encode("ascii"))
    except InvalidToken as error:
        raise ValueError(
            "decrypt_secret: невалидный Fernet-токен (или несовпадающий secrets.encryption_key)"
        ) from error
    return plain.decode("utf-8")


def mask_secret_plaintext(plaintext: str | None) -> str:
    """Возвращает '**** abcd' (последние 4 символа). Для None/пусто — '****'."""
    if plaintext is None or not plaintext.strip():
        return "****"
    tail = (
        plaintext[-_SECRET_MASK_VISIBLE_TAIL:]
        if len(plaintext) >= _SECRET_MASK_VISIBLE_TAIL
        else plaintext
    )
    return f"**** {tail}"


__all__ = [
    "decrypt_secret",
    "encrypt_secret",
    "mask_secret_plaintext",
]
