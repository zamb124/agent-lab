"""
CacheResource - wrapper для cache ресурса.

Предоставляет доступ к Redis cache.
"""

from typing import Any, Optional

from core.logging import get_logger

logger = get_logger(__name__)


class CacheResource:
    """
    Ресурс для работы с Redis cache.
    
    Пример:
        # Кэширование результата
        result = await cache.get("user:123")
        if result is None:
            result = await fetch_user(123)
            await cache.set("user:123", result)
    """
    
    def __init__(
        self,
        namespace: str,
        ttl: int = 3600,
        container: Any = None,
    ):
        self.namespace = namespace
        self.ttl = ttl
        self._container = container
    
    def _get_key(self, key: str) -> str:
        """Возвращает полный ключ с namespace."""
        return f"{self.namespace}:{key}"
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Получить значение из кэша.
        
        Args:
            key: Ключ
            
        Returns:
            Значение или None
        """
        import json
        
        from apps.flows.src.container import get_container
        container = self._container or get_container()
        
        full_key = self._get_key(key)
        value = await container.redis_client.get(full_key)
        
        if value is None:
            return None
        
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Установить значение в кэш.
        
        Args:
            key: Ключ
            value: Значение
            ttl: TTL в секундах (по умолчанию из конфига)
            
        Returns:
            True если успешно
        """
        import json
        
        from apps.flows.src.container import get_container
        container = self._container or get_container()
        
        full_key = self._get_key(key)
        
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, (int, float)):
            value = str(value)
        
        await container.redis_client.set(
            full_key,
            value,
            ttl=ttl or self.ttl,
        )
        return True
    
    async def delete(self, key: str) -> bool:
        """
        Удалить значение из кэша.
        
        Args:
            key: Ключ
            
        Returns:
            True если удалено
        """
        from apps.flows.src.container import get_container
        container = self._container or get_container()
        
        full_key = self._get_key(key)
        result = await container.redis_client.delete(full_key)
        return result > 0
    
    async def exists(self, key: str) -> bool:
        """
        Проверить существование ключа.
        
        Args:
            key: Ключ
            
        Returns:
            True если существует
        """
        from apps.flows.src.container import get_container
        container = self._container or get_container()
        
        full_key = self._get_key(key)
        value = await container.redis_client.get(full_key)
        return value is not None
    
    async def incr(self, key: str, amount: int = 1) -> int:
        """
        Инкремент счётчика.
        
        Args:
            key: Ключ
            amount: Значение инкремента
            
        Returns:
            Новое значение
        """
        from apps.flows.src.container import get_container
        container = self._container or get_container()
        
        full_key = self._get_key(key)
        
        current = await container.redis_client.get(full_key)
        current_value = int(current) if current else 0
        new_value = current_value + amount
        
        await container.redis_client.set(full_key, str(new_value), ttl=self.ttl)
        return new_value
    
    def __repr__(self) -> str:
        return f"<CacheResource namespace={self.namespace} ttl={self.ttl}>"
