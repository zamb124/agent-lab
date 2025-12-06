"""
Единый HTTP клиент для межсервисного взаимодействия.

Автоматически:
- Добавляет заголовки из контекста (X-Trace-Id, Authorization, X-Company-Id, X-User-Id)
- Загружает и кэширует OpenAPI спеки сервисов
- Валидирует запросы по OpenAPI перед отправкой
"""

import asyncio
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

import httpx

from core.context import get_context
from core.config import get_settings
from core.http import get_httpx_client

logger = logging.getLogger(__name__)

TRACE_ID_HEADER = "X-Trace-Id"
COMPANY_ID_HEADER = "X-Company-Id"
USER_ID_HEADER = "X-User-Id"

OPENAPI_REFRESH_INTERVAL = 15  # секунд


class ServiceClientError(Exception):
    """Ошибка межсервисного взаимодействия"""
    pass


class ServiceValidationError(ServiceClientError):
    """Ошибка валидации запроса по OpenAPI"""
    pass


class ServiceClient:
    """
    Единый клиент для межсервисного взаимодействия.
    
    Знает все сервисы, автоматически добавляет заголовки из контекста,
    периодически обновляет OpenAPI спеки и валидирует запросы.
    """
    
    def __init__(self):
        self._specs_cache: Dict[str, dict] = {}
        self._specs_last_update: Dict[str, datetime] = {}
        self._refresh_task: Optional[asyncio.Task] = None
        self._running = False
        self._known_services = ["agents", "crm", "frontend"]
    
    def _get_service_url(self, service: str) -> str:
        """Получает URL сервиса из конфигурации"""
        settings = get_settings()
        return settings.server.get_service_url(service)
    
    def _get_openapi_url(self, service: str) -> str:
        """Получает URL OpenAPI спеки сервиса"""
        base_url = self._get_service_url(service)
        # OpenAPI спека всегда по пути /openapi.json
        return f"{base_url}/openapi.json"
    
    def _build_headers(self) -> Dict[str, str]:
        """Собирает заголовки из текущего контекста"""
        headers = {"Content-Type": "application/json"}
        
        context = get_context()
        if not context:
            return headers
        
        if context.trace_id:
            headers[TRACE_ID_HEADER] = context.trace_id
        
        if context.auth_token:
            headers["Authorization"] = f"Bearer {context.auth_token}"
        
        if context.active_company:
            headers[COMPANY_ID_HEADER] = context.active_company.company_id
        
        if context.user:
            headers[USER_ID_HEADER] = context.user.user_id
        
        return headers
    
    async def _fetch_openapi_spec(self, service: str) -> Optional[dict]:
        """Загружает OpenAPI спеку сервиса"""
        url = self._get_openapi_url(service)
        
        try:
            async with get_httpx_client(timeout=5.0, use_proxy_from_config=False) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.warning(f"Не удалось загрузить OpenAPI спеку для {service}: {e}")
            return None
    
    async def _refresh_all_specs(self):
        """Обновляет OpenAPI спеки всех сервисов"""
        for service in self._known_services:
            spec = await self._fetch_openapi_spec(service)
            if spec:
                self._specs_cache[service] = spec
                self._specs_last_update[service] = datetime.now(timezone.utc)
                logger.debug(f"OpenAPI спека для {service} обновлена")
    
    async def _refresh_loop(self):
        """Фоновый цикл обновления спек"""
        while self._running:
            try:
                await self._refresh_all_specs()
            except Exception as e:
                logger.error(f"Ошибка обновления OpenAPI спек: {e}")
            
            await asyncio.sleep(OPENAPI_REFRESH_INTERVAL)
    
    async def start(self):
        """Запускает фоновое обновление спек"""
        if self._running:
            return
        
        self._running = True
        
        # Загружаем спеки при старте
        await self._refresh_all_specs()
        
        # Запускаем фоновое обновление
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info("ServiceClient запущен, фоновое обновление OpenAPI спек активно")
    
    async def stop(self):
        """Останавливает фоновое обновление"""
        self._running = False
        
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None
        
        logger.info("ServiceClient остановлен")
    
    def _validate_request(self, service: str, method: str, path: str) -> bool:
        """
        Валидирует запрос по OpenAPI спеке.
        
        Проверяет что path и method существуют в спеке сервиса.
        Если спека недоступна - пропускает валидацию с warning.
        
        Returns:
            True если валидация прошла или спека недоступна
            
        Raises:
            ServiceValidationError: если path/method не найдены в спеке
        """
        spec = self._specs_cache.get(service)
        if not spec:
            logger.warning(f"OpenAPI спека для {service} недоступна, пропускаем валидацию")
            return True
        
        paths = spec.get("paths", {})
        
        # Нормализуем path (убираем параметры для поиска)
        normalized_path = self._normalize_path(path, paths)
        
        if normalized_path not in paths:
            raise ServiceValidationError(
                f"Path '{path}' не найден в OpenAPI спеке сервиса {service}"
            )
        
        allowed_methods = [m.upper() for m in paths[normalized_path].keys() if m != "parameters"]
        if method.upper() not in allowed_methods:
            raise ServiceValidationError(
                f"Method '{method}' не разрешен для path '{path}' в сервисе {service}. "
                f"Разрешены: {allowed_methods}"
            )
        
        return True
    
    def _normalize_path(self, path: str, spec_paths: dict) -> str:
        """
        Нормализует path для поиска в OpenAPI спеке.
        
        Заменяет конкретные значения на параметры шаблона.
        Например: /users/123 -> /users/{user_id}
        """
        # Сначала пробуем точное совпадение
        if path in spec_paths:
            return path
        
        # Пробуем найти шаблонный путь
        path_parts = path.strip("/").split("/")
        
        for spec_path in spec_paths:
            spec_parts = spec_path.strip("/").split("/")
            
            if len(spec_parts) != len(path_parts):
                continue
            
            match = True
            for spec_part, path_part in zip(spec_parts, path_parts):
                # Параметр в фигурных скобках
                if spec_part.startswith("{") and spec_part.endswith("}"):
                    continue
                if spec_part != path_part:
                    match = False
                    break
            
            if match:
                return spec_path
        
        return path
    
    async def request(
        self,
        service: str,
        method: str,
        path: str,
        validate: bool = True,
        timeout: float = 30.0,
        **kwargs
    ) -> Any:
        """
        Выполняет HTTP запрос к сервису.
        
        Args:
            service: Имя сервиса (agents, crm, frontend)
            method: HTTP метод (GET, POST, PUT, DELETE)
            path: Путь запроса (без базового URL)
            validate: Валидировать ли запрос по OpenAPI
            timeout: Таймаут запроса
            **kwargs: Дополнительные параметры для httpx
            
        Returns:
            Ответ сервиса (JSON)
            
        Raises:
            ServiceValidationError: если валидация не прошла
            ServiceClientError: если запрос не удался
        """
        if validate:
            self._validate_request(service, method, path)
        
        base_url = self._get_service_url(service)
        url = f"{base_url}{path}"
        
        headers = self._build_headers()
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        
        try:
            async with get_httpx_client(timeout=timeout, use_proxy_from_config=False) as client:
                response = await client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                
                if response.content:
                    return response.json()
                return None
                
        except httpx.HTTPStatusError as e:
            raise ServiceClientError(
                f"HTTP ошибка {e.response.status_code} при запросе к {service}: {e.response.text}"
            )
        except Exception as e:
            raise ServiceClientError(f"Ошибка запроса к {service}: {e}")
    
    async def get(self, service: str, path: str, **kwargs) -> Any:
        """GET запрос к сервису"""
        return await self.request(service, "GET", path, **kwargs)
    
    async def post(self, service: str, path: str, **kwargs) -> Any:
        """POST запрос к сервису"""
        return await self.request(service, "POST", path, **kwargs)
    
    async def put(self, service: str, path: str, **kwargs) -> Any:
        """PUT запрос к сервису"""
        return await self.request(service, "PUT", path, **kwargs)
    
    async def delete(self, service: str, path: str, **kwargs) -> Any:
        """DELETE запрос к сервису"""
        return await self.request(service, "DELETE", path, **kwargs)
    
    def get_spec(self, service: str) -> Optional[dict]:
        """Возвращает кэшированную OpenAPI спеку сервиса"""
        return self._specs_cache.get(service)
    
    def get_available_paths(self, service: str) -> list:
        """Возвращает список доступных путей сервиса"""
        spec = self._specs_cache.get(service)
        if not spec:
            return []
        return list(spec.get("paths", {}).keys())


# Синглтон
_service_client: Optional[ServiceClient] = None


def get_service_client() -> ServiceClient:
    """Получает синглтон ServiceClient"""
    global _service_client
    if _service_client is None:
        _service_client = ServiceClient()
    return _service_client


async def init_service_client():
    """Инициализирует и запускает ServiceClient"""
    client = get_service_client()
    await client.start()
    return client


async def shutdown_service_client():
    """Останавливает ServiceClient"""
    global _service_client
    if _service_client:
        await _service_client.stop()

