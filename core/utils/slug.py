"""
Утилиты для генерации и работы со slug.
"""

import hashlib
import re


def generate_slug(
    name: str,
    max_length: int = 47,
    min_length: int = 3,
    add_hash: bool = False,
    hash_length: int = 6
) -> str:
    """
    Генерирует валидный slug из строки.

    Правила:
    - Только lowercase буквы, цифры и дефисы
    - Не начинается и не заканчивается дефисом
    - Не содержит двойных дефисов
    - Длина меньше 48 символов

    Args:
        name: Строка для преобразования в slug
        max_length: Максимальная длина slug
        min_length: Минимальная длина slug
        add_hash: Добавить хэш для гарантии уникальности
        hash_length: Длина хэша

    Returns:
        Валидный slug

    Examples:
        >>> generate_slug("My Company Name")
        'my-company-name'
        >>> generate_slug("My Company", add_hash=True)
        'my-company-a1b2c3'
    """
    if not name:
        name = "entity"

    slug = name.lower()
    slug = re.sub(r'[^a-z0-9-]', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')

    if add_hash:
        name_hash = hashlib.md5(name.encode()).hexdigest()[:hash_length]
        max_base_len = max_length - hash_length - 1
        slug = f"{slug[:max_base_len]}-{name_hash}"
    else:
        slug = slug[:max_length]

    slug = slug.rstrip('-')

    if len(slug) < min_length:
        slug = f"{slug}-entity"[:max_length]

    return slug

