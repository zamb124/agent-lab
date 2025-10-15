"""
Утилиты для генерации и работы со slug.
Единая точка правды для всех slug в системе.
"""

import re
import hashlib
from typing import Optional


def generate_slug(
    name: str,
    max_length: int = 63,
    min_length: int = 3,
    add_hash: bool = False,
    hash_length: int = 8
) -> str:
    """
    Генерирует валидный slug из строки.
    
    Правила:
    - Только lowercase буквы, цифры и дефисы
    - Не начинается и не заканчивается дефисом
    - Не содержит двойных дефисов
    - Длина от min_length до max_length символов
    
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
        'my-company-a1b2c3d4'
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

def generate_flow_slug(flow_id: str, flow_name: Optional[str] = None) -> str:
    """
    Генерирует slug для flow.
    
    Args:
        flow_id: ID flow
        flow_name: Название flow (если есть)
        
    Returns:
        Slug flow
    """
    if flow_name:
        return generate_slug(flow_name, add_hash=True)
    return generate_slug(f"flow-{flow_id}", add_hash=True)


def generate_session_slug(session_id: str) -> str:
    """
    Генерирует slug для сессии.
    
    Args:
        session_id: ID сессии
        
    Returns:
        Slug сессии
    """
    return generate_slug(f"session-{session_id}", add_hash=True)


