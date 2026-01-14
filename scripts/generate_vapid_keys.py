#!/usr/bin/env python3
"""
Генерация VAPID ключей для Web Push уведомлений.

Использование:
    python scripts/generate_vapid_keys.py

Ключи будут выведены в консоль. Добавьте их в conf.local.json:
{
    "push": {
        "enabled": true,
        "vapid_public_key": "<PUBLIC_KEY>",
        "vapid_private_key": "<PRIVATE_KEY>",
        "vapid_email": "admin@humanitec.ru"
    }
}
"""

import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization


def b64url_encode(data: bytes) -> str:
    """URL-safe base64 encoding without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def generate_vapid_keys():
    """Генерирует пару VAPID ключей."""
    # Генерируем EC ключ на кривой P-256 (SECP256R1)
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()
    
    # Экспортируем private key как raw bytes (32 байта)
    private_numbers = private_key.private_numbers()
    private_bytes = private_numbers.private_value.to_bytes(32, 'big')
    
    # Экспортируем public key в формате X9.62 uncompressed (65 байт)
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    
    return b64url_encode(public_bytes), b64url_encode(private_bytes)


def main():
    public_key, private_key = generate_vapid_keys()
    
    print("\n" + "=" * 60)
    print("VAPID Keys для Web Push Notifications")
    print("=" * 60)
    print()
    print(f"PUBLIC_KEY:  {public_key}")
    print(f"PRIVATE_KEY: {private_key}")
    print()
    print("Добавьте в conf.local.json:")
    print()
    print('''{
  "push": {
    "enabled": true,
    "vapid_public_key": "''' + public_key + '''",
    "vapid_private_key": "''' + private_key + '''",
    "vapid_email": "admin@humanitec.ru"
  }
}''')
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
