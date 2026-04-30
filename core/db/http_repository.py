"""
HTTP прокси для удаленных репозиториев.

Когда сервис обращается к репозиторию другого сервиса,
вместо прямого доступа к БД используются HTTP запросы к API.

ЛЮБОЙ метод репозитория автоматически проксируется через HTTP.
"""

from core.logging import get_logger
from typing import Generic, TypeVar, Type, Any, Callable

from pydantic import BaseModel

from core.context import get_context
from core.http import get_httpx_client

logger = get_logger(__name__)
T = TypeVar('T', bound=BaseModel)

class HTTPRepositoryProxy(Generic[T]):
    """
    HTTP прокси для репозитория другого сервиса.
    
    Динамически проксирует ВСЕ методы репозитория через HTTP.
    Использует __getattr__ для перехвата любых вызовов методов.
    """
    
    def __init__(
        self,
        repository_class: Type,
        model_class: Type[T]
    ):
        """
        Args:
            repository_class: Класс репозитория (для получения URL и prefix)
            model_class: Класс Pydantic модели
        """
        self.repository_class = repository_class
        self.model_class = model_class
        self.repository_prefix = repository_class.api_prefix
        self.owner_service = repository_class.owner_service
    
    def _get_base_url(self) -> str:
        """Формирует базовый URL для API запросов"""
        service_url = self.repository_class.get_service_url()
        return f"{service_url}/{self.owner_service}/api/v1/{self.repository_prefix}"
    
    async def _request(
        self,
        method: str,
        path: str = "",
        **kwargs
    ) -> Any:
        """
        Выполняет HTTP запрос к API сервиса-владельца.
        Передает контекст (trace_id, company_id, user_id) в заголовках.
        """
        context = get_context()
        headers = kwargs.pop("headers", {})
        
        if context:
            if context.trace_id:
                headers["X-Trace-Id"] = context.trace_id
            if context.auth_token:
                headers["Authorization"] = f"Bearer {context.auth_token}"
            if context.active_company:
                headers["X-Company-Id"] = context.active_company.company_id
            if context.user:
                headers["X-User-Id"] = context.user.user_id
        
        url = f"{self._get_base_url()}{path}"
        
        logger.info(f"HTTPRepositoryProxy request: {method} {url}, trace_id={headers.get('X-Trace-Id')}")
        
        async with get_httpx_client(timeout=30.0) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            
            if response.content:
                return response.json()
            return None
    
    def __getattr__(self, name: str) -> Callable:
        """
        Перехватывает вызовы любых методов и проксирует через HTTP.
        
        Соглашение:
        - Метод репозитория → POST /{method_name}
        - Аргументы передаются в JSON body
        - Результат десериализуется в model_class если это dict/list
        """
        if name.startswith('_'):
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
        
        async def proxy_method(*args, **kwargs) -> Any:
            # Собираем все аргументы в payload
            payload = {
                "args": list(args),
                "kwargs": kwargs
            }
            
            try:
                result = await self._request("POST", f"/method/{name}", json=payload)
            except Exception as e:
                if "404" in str(e):
                    raise AttributeError(
                        f"Метод '{name}' не найден в репозитории {self.repository_class.__name__}"
                    )
                raise
            
            return self._deserialize_result(result)
        
        return proxy_method
    
    def _deserialize_result(self, result: Any) -> Any:
        """Десериализует результат в модель если возможно"""
        if result is None:
            return None
        
        if isinstance(result, dict) and self.model_class:
            return self.model_class.model_validate(result)
        
        if isinstance(result, list) and self.model_class:
            return [self.model_class.model_validate(item) for item in result]
        
        return result
    
    # Стандартные методы для обратной совместимости (оптимизированные пути)
    
    async def get(self, entity_id: str):
        """GET /{entity_id}"""
        try:
            data = await self._request("GET", f"/{entity_id}")
            return self._deserialize_result(data)
        except Exception as e:
            if "404" in str(e):
                return None
            raise
    
    async def set(self, entity) -> bool:
        """POST /"""
        entity_data = entity.model_dump(mode="json") if hasattr(entity, 'model_dump') else entity
        await self._request("POST", "", json=entity_data)
        return True
    
    async def delete(self, entity_id: str) -> bool:
        """DELETE /{entity_id}"""
        try:
            await self._request("DELETE", f"/{entity_id}")
            return True
        except Exception as e:
            if "404" in str(e):
                return False
            raise
    
    async def list(self, *, limit: int, offset: int = 0):
        """GET /?limit={limit}&offset={offset}"""
        data = await self._request("GET", "", params={"limit": limit, "offset": offset})
        return self._deserialize_result(data) if data else []
    
    async def get_many(self, entity_ids: list):
        """POST /many"""
        if not entity_ids:
            return {}
        data = await self._request("POST", "/many", json=entity_ids)
        if not data:
            return {}
        # Десериализуем каждое значение
        if self.model_class:
            return {
                k: self.model_class.model_validate(v) if isinstance(v, dict) else v
                for k, v in data.items()
            }
        return data
