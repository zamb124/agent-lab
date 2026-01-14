"""
Утилиты для работы с доменами.
Поддержка нескольких доменов (humanitec.ru, agents-lab.ru) и localhost.
"""

PRIMARY_DOMAIN = "humanitec.ru"
SUPPORTED_DOMAINS = ["humanitec.ru", "agents-lab.ru"]


def extract_base_domain(host: str) -> str:
    """
    Извлекает базовый домен из Host header.
    
    Примеры:
        humanitec.ru → humanitec.ru
        www.humanitec.ru → humanitec.ru
        company.humanitec.ru → humanitec.ru
        agents-lab.ru → agents-lab.ru
        company.agents-lab.ru → agents-lab.ru
        localhost:8002 → localhost
        company.localhost:8002 → localhost
        lvh.me:8002 → lvh.me
        company.lvh.me:8002 → lvh.me
    """
    host_without_port = host.split(":")[0].lower()
    
    # localhost обрабатываем отдельно
    if host_without_port == "localhost" or host_without_port.endswith(".localhost"):
        return "localhost"
    
    # lvh.me (магический домен для dev с субдоменами, резолвится в 127.0.0.1)
    if host_without_port == "lvh.me" or host_without_port.endswith(".lvh.me"):
        return "lvh.me"
    
    for domain in SUPPORTED_DOMAINS:
        if host_without_port == domain or host_without_port.endswith(f".{domain}"):
            return domain
    
    return PRIMARY_DOMAIN


def extract_subdomain(host: str) -> str | None:
    """
    Извлекает subdomain из Host header.
    
    Примеры:
        humanitec.ru → None
        www.humanitec.ru → None
        company.humanitec.ru → company
        my-company.agents-lab.ru → my-company
        localhost → None
        company.localhost:8002 → company
    """
    base = extract_base_domain(host)
    host_without_port = host.split(":")[0].lower()
    
    if host_without_port == base or host_without_port == f"www.{base}":
        return None
    
    if host_without_port.endswith(f".{base}"):
        return host_without_port.removesuffix(f".{base}")
    
    return None


def is_local(host: str) -> bool:
    """Проверяет, является ли host локальным (localhost или lvh.me)."""
    base = extract_base_domain(host)
    return base == "localhost" or base == "lvh.me"


def is_supported_domain(host: str) -> bool:
    """Проверяет, является ли host одним из поддерживаемых доменов, localhost или lvh.me."""
    base = extract_base_domain(host)
    return base == "localhost" or base == "lvh.me" or base in SUPPORTED_DOMAINS


def get_protocol(host: str) -> str:
    """Возвращает протокол: http для localhost, https для production."""
    return "http" if is_local(host) else "https"


def get_host_with_port(host: str) -> str:
    """
    Возвращает базовый домен с портом для localhost и lvh.me.
    
    Примеры:
        localhost:8002 → localhost:8002
        company.localhost:8002 → localhost:8002
        lvh.me:8002 → lvh.me:8002
        company.lvh.me:8002 → lvh.me:8002
        humanitec.ru → humanitec.ru
        company.humanitec.ru → humanitec.ru
    """
    base = extract_base_domain(host)
    
    if base == "localhost" or base == "lvh.me":
        # Сохраняем порт для localhost и lvh.me
        port = host.split(":")[-1] if ":" in host else "8002"
        return f"{base}:{port}"
    
    return base


def get_cookie_domain(host: str) -> str | None:
    """
    Возвращает домен для установки cookie (с точкой в начале для работы на субдоменах)
    
    Примеры:
        localhost:8002 → None (куки на localhost не поддерживают субдомены)
        company.localhost:8002 → None
        lvh.me:8002 → .lvh.me (работает корректно!)
        company.lvh.me:8002 → .lvh.me
        humanitec.ru → .humanitec.ru
        company.humanitec.ru → .humanitec.ru
    
    Returns:
        Домен для cookie с точкой в начале, или None для localhost
    
    Note:
        Для localhost возвращаем None, так как браузеры не поддерживают
        куки на .localhost с субдоменами. Для dev используйте lvh.me - это магический
        домен, который резолвится в 127.0.0.1 и корректно работает с куками на субдоменах.
    """
    base = extract_base_domain(host)
    
    # Для localhost не устанавливаем domain - браузеры не поддерживают .localhost
    if base == "localhost":
        return None
    
    return f".{base}"


def build_url(host: str, path: str = "", subdomain: str | None = None) -> str:
    """
    Строит полный URL с учетом текущего домена.
    
    Args:
        host: Host header из запроса
        path: Путь (начинается с /)
        subdomain: Поддомен (опционально)
    
    Returns:
        Полный URL (http для localhost, https для production)
    """
    protocol = get_protocol(host)
    base = get_host_with_port(host)
    
    if subdomain:
        return f"{protocol}://{subdomain}.{base}{path}"
    
    return f"{protocol}://{base}{path}"

