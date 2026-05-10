"""
Утилиты для работы с субдоменами и slug'ами компаний
"""
import re
import uuid
from typing import Optional


# Таблица транслитерации кириллицы
TRANSLIT_MAP = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
    'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
    'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo', 'Ж': 'Zh',
    'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N', 'О': 'O',
    'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'H', 'Ц': 'Ts',
    'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch', 'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
}


def _transliterate(text: str) -> str:
    """
    Транслитерация кириллицы в латиницу
    
    Args:
        text: Текст с кириллицей
    
    Returns:
        Транслитерированный текст
    """
    result = []
    for char in text:
        result.append(TRANSLIT_MAP.get(char, char))
    return ''.join(result)


def slugify(text: str) -> str:
    """
    Преобразует текст в валидный subdomain slug
    
    - Транслитерация кириллицы
    - Lowercase
    - Замена пробелов и спецсимволов на дефис
    - Удаление множественных дефисов
    - Валидация длины (минимум 3, максимум 63 символа)
    
    Args:
        text: Исходный текст (например, название компании)
    
    Returns:
        Валидный slug для использования в субдомене
    
    Examples:
        >>> slugify("Моя Компания")
        'moya-kompaniya'
        >>> slugify("ABC Inc.")
        'abc-inc'
    """
    if not text:
        return f"company-{uuid.uuid4().hex[:6]}"
    
    # Транслитерация кириллицы
    text = _transliterate(text)
    
    # Lowercase и замена спецсимволов на дефис
    text = text.lower()
    text = re.sub(r'[^a-z0-9-]', '-', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    
    # Валидация длины
    if len(text) < 3:
        text = f"{text}-{uuid.uuid4().hex[:6]}"
    if len(text) > 63:
        text = text[:63].rstrip('-')
    
    return text


def build_subdomain_url(subdomain: str, path: str = "/", env: str = "production", port: int = 8002) -> str:
    """
    Формирует полный URL с субдоменом
    
    Args:
        subdomain: Субдомен компании
        path: Путь (например /dashboard)
        env: Окружение (production для https, иначе http)
        port: Порт для non-production (по умолчанию 8002)
    
    Returns:
        Полный URL с субдоменом
    
    Examples:
        >>> build_subdomain_url("mycompany", "/dashboard", "development")
        'http://mycompany.lvh.me:8002/dashboard'
        >>> build_subdomain_url("mycompany", "/dashboard", "production")
        'https://mycompany.humanitec.ru/dashboard'
    
    Note:
        Для dev используем lvh.me вместо localhost, так как браузеры не поддерживают
        куки на .localhost с субдоменами. lvh.me автоматически резолвится в 127.0.0.1.
    """
    if env == "production":
        # Production: https + humanitec.ru
        return f"https://{subdomain}.humanitec.ru{path}"
    else:
        # Development/local: http + lvh.me с портом (lvh.me резолвится в 127.0.0.1)
        return f"http://{subdomain}.lvh.me:{port}{path}"


def validate_slug(slug: str) -> tuple[bool, Optional[str]]:
    """
    Валидирует slug для использования в субдомене
    
    Args:
        slug: Проверяемый slug
    
    Returns:
        Кортеж (валидность, сообщение об ошибке)
    
    Examples:
        >>> validate_slug("mycompany")
        (True, None)
        >>> validate_slug("ab")
        (False, "Минимальная длина - 3 символа")
    """
    if not slug:
        return False, "Slug не может быть пустым"
    
    if len(slug) < 3:
        return False, "Минимальная длина - 3 символа"
    
    if len(slug) > 63:
        return False, "Максимальная длина - 63 символа"
    
    if not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$', slug):
        return False, "Только латинские буквы, цифры и дефис. Должен начинаться и заканчиваться буквой или цифрой"
    
    # Зарезервированные slug'и (субдомен тенанта; onlyoffice — хост Document Server в проде;
    # grafana/loki/tempo/alloy — observability-стек; livekit — WebRTC-сервер; cdn — статика/embed)
    reserved = [
        "www",
        "api",
        "admin",
        "static",
        "cdn",
        "system",
        "test",
        "staging",
        "production",
        "localhost",
        "onlyoffice",
        "grafana",
        "loki",
        "tempo",
        "alloy",
        "livekit",
    ]
    if slug in reserved:
        return False, f"'{slug}' - зарезервированное имя"
    
    return True, None

