"""
HTTPResource - wrapper для http ресурса.

Предоставляет доступ к внешним HTTP API.
"""

import base64
from typing import Any, Dict, Optional

from core.logging import get_logger
from core.http import get_httpx_client

logger = get_logger(__name__)


class HTTPResource:
    """
    Ресурс для работы с HTTP API.
    
    Пример:
        order = await order_api.get(f"/orders/{order_id}")
        
        result = await api.post("/users", json={"name": "John"})
    """
    
    def __init__(
        self,
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        auth_type: Optional[str] = None,
        auth_value: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self.auth_type = auth_type
        self.auth_value = auth_value
        
        # Добавляем auth header если указан
        if auth_type and auth_value:
            if auth_type == "bearer":
                self.headers["Authorization"] = f"Bearer {auth_value}"
            elif auth_type == "api_key":
                self.headers["X-API-Key"] = auth_value
            elif auth_type == "basic":
                encoded = base64.b64encode(auth_value.encode()).decode()
                self.headers["Authorization"] = f"Basic {encoded}"
    
    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """
        GET запрос.
        
        Args:
            path: Путь (относительно base_url)
            params: Query параметры
            headers: Дополнительные заголовки
            
        Returns:
            JSON ответ
        """
        return await self._request("GET", path, params=params, headers=headers)
    
    async def post(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """
        POST запрос.
        
        Args:
            path: Путь
            json: JSON body
            data: Form data
            headers: Дополнительные заголовки
            
        Returns:
            JSON ответ
        """
        return await self._request("POST", path, json=json, data=data, headers=headers)
    
    async def put(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """PUT запрос."""
        return await self._request("PUT", path, json=json, headers=headers)
    
    async def patch(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """PATCH запрос."""
        return await self._request("PATCH", path, json=json, headers=headers)
    
    async def delete(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """DELETE запрос."""
        return await self._request("DELETE", path, headers=headers)
    
    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        
        merged_headers = {**self.headers}
        if headers:
            merged_headers.update(headers)
        
        async with get_httpx_client(timeout=self.timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                params=params,
                json=json,
                data=data,
                headers=merged_headers,
            )
            response.raise_for_status()
            
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.json()
            return response.text
    
    def __repr__(self) -> str:
        return f"<HTTPResource base_url={self.base_url}>"
