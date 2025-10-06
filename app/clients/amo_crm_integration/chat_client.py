"""
AmoCRM Chat API клиент для работы с чатами через amojo.amocrm.ru

ВАЖНО: Chat API использует отдельную авторизацию через подпись (HMAC SHA1),
отличную от обычного OAuth 2.0. Требуется scope_id и secret_key от интеграции.
"""

import hashlib
import hmac
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
from email.utils import formatdate
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Константы
CONTENT_TYPE_JSON = "application/json"

# Глобальный кеш для singleton клиентов
_chat_client_cache: Dict[tuple, "AmoCRMChatClient"] = {}


class ChatMessage(BaseModel):
    """Модель сообщения в чате"""

    id: Optional[str] = None
    conversation_id: str
    author: Dict[str, Any]
    type: str
    text: Optional[str] = None
    timestamp: Optional[int] = None
    media: Optional[List[Dict[str, Any]]] = None


class AmoCRMChatClient:
    """
    Клиент для работы с AmoCRM Chat API (amojo.amocrm.ru)

    Поддерживает:
    - Отправку сообщений в чаты
    - Создание и управление разговорами
    - Обновление статусов сообщений
    - Импорт истории переписки
    """

    def __init__(
        self,
        channel_id: str,
        secret_key: str,
        account_id: Optional[str] = None,
    ):
        """
        Инициализация клиента AmoCRM Chat API

        Args:
            channel_id: ID канала из регистрации (для нового канала) или scope_id (для существующего)
            secret_key: Секретный ключ интеграции для подписи запросов
            account_id: ID аккаунта AmoCRM (amojo_id), опционален для connect
        """
        self.channel_id = channel_id
        self.secret_key = secret_key
        self.account_id = account_id
        self.base_url = "https://amojo.amocrm.ru"

        self._client: Optional[httpx.AsyncClient] = None

        logger.info(f"AmoCRM Chat клиент инициализирован для channel_id: {channel_id}")

    def _get_client(self) -> httpx.AsyncClient:
        """Получает или создает HTTP клиент"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        """Закрывает HTTP клиент"""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _generate_signature(self, method: str, path: str, body: str, content_type: str, date: str) -> tuple[str, str]:
        """
        Генерирует подпись для запроса к Chat API

        Args:
            method: HTTP метод (POST, GET)
            path: Путь запроса
            body: Тело запроса (JSON)
            content_type: Content-Type заголовок
            date: Дата в формате RFC2822

        Returns:
            Кортеж (signature, content_md5)
        """
        # Вычисляем MD5 от тела запроса
        content_md5 = hashlib.md5(body.encode()).hexdigest().lower()

        # Формируем строку для подписи
        sign_string = "\n".join([method.upper(), content_md5, content_type, date, path])

        # Генерируем HMAC SHA1 подпись
        signature = hmac.new(self.secret_key.encode(), sign_string.encode(), hashlib.sha1).hexdigest().lower()

        return signature, content_md5

    async def connect_channel(
        self,
        account_id: str,
        title: str = "Мой канал",
        hook_api_version: str = "v2",
        is_time_window_disabled: bool = False,
    ) -> Dict[str, Any]:
        """
        Подключает канал чата к аккаунту AmoCRM

        Этот метод необходимо вызвать ОДИН раз при первом подключении канала
        к аккаунту. После подключения можно отправлять сообщения.

        Args:
            account_id: amojo_id аккаунта AmoCRM
            title: Название канала (отображается в интерфейсе AmoCRM)
            hook_api_version: Версия API для webhook'ов (по умолчанию "v2")
            is_time_window_disabled: Отключение временного окна канала

        Returns:
            Ответ от API с информацией о подключенном канале (включая scope_id)

        Raises:
            httpx.HTTPStatusError: При ошибке подключения канала
        """
        client = self._get_client()

        path = f"/v2/origin/custom/{self.channel_id}/connect"
        method = "POST"
        content_type = CONTENT_TYPE_JSON
        date = formatdate(timeval=None, localtime=False, usegmt=True)

        payload = {
            "account_id": account_id,
            "title": title,
            "hook_api_version": hook_api_version,
            "is_time_window_disabled": is_time_window_disabled,
        }

        import json

        body = json.dumps(payload)

        # Генерируем подпись
        signature, content_md5 = self._generate_signature(method, path, body, content_type, date)

        headers = {
            "Date": date,
            "Content-Type": content_type,
            "Content-MD5": content_md5,
            "X-Signature": signature,
        }

        try:
            response = await client.post(f"{self.base_url}{path}", content=body, headers=headers)
            response.raise_for_status()

            result = response.json() if response.text else {}
            logger.info(f"Канал '{title}' успешно подключен к аккаунту {account_id}")
            logger.info(f"Получен scope_id: {result.get('scope_id')}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось подключить канал к аккаунту (account_id={account_id}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def send_message(
        self,
        conversation_id: str,
        user_id: str,
        user_name: str,
        text: Optional[str] = None,
        message_type: str = "text",
        media: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Отправляет сообщение в чат (создает разговор если нужно)

        Args:
            conversation_id: Уникальный ID разговора
            user_id: Уникальный ID пользователя в вашей системе
            user_name: Имя пользователя
            text: Текст сообщения
            message_type: Тип сообщения ("text", "picture", "file", etc.)
            media: Список медиафайлов
            user_profile: Дополнительная информация о пользователе (phone, email)

        Returns:
            Ответ от API
        """
        if not self.account_id:
            raise ValueError("account_id обязателен для отправки сообщений. Укажите его при создании клиента.")

        client = self._get_client()

        # Для отправки сообщений используется scope_id (channel_id после connect)
        path = f"/v2/origin/custom/{self.channel_id}"
        method = "POST"
        content_type = CONTENT_TYPE_JSON
        date = formatdate(timeval=None, localtime=False, usegmt=True)

        # Формируем тело запроса
        payload = {
            "account_id": self.account_id,
            "conversation_id": conversation_id,
            "user": {
                "id": user_id,
                "name": user_name,
            },
            "message": {
                "type": message_type,
            },
        }

        if text:
            payload["message"]["text"] = text

        if media:
            payload["message"]["media"] = media

        if user_profile:
            payload["user"]["profile"] = user_profile

        import json

        body = json.dumps(payload)

        # Генерируем подпись
        signature, content_md5 = self._generate_signature(method, path, body, content_type, date)

        headers = {
            "Date": date,
            "Content-Type": content_type,
            "Content-MD5": content_md5,
            "X-Signature": signature,
        }

        try:
            response = await client.post(f"{self.base_url}{path}", content=body, headers=headers)
            response.raise_for_status()

            result = response.json() if response.text else {}
            logger.info(f"Сообщение отправлено в разговор {conversation_id}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось отправить сообщение в Chat API (conversation_id={conversation_id}): "
                f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e

    async def update_message_status(
        self,
        conversation_id: str,
        message_id: str,
        status: str,
    ) -> Dict[str, Any]:
        """
        Обновляет статус отправленного сообщения

        Args:
            conversation_id: ID разговора
            message_id: ID сообщения
            status: Статус ("delivered", "read", "error")

        Returns:
            Ответ от API
        """
        if not self.account_id:
            raise ValueError("account_id обязателен для обновления статуса. Укажите его при создании клиента.")

        client = self._get_client()

        # Для отправки сообщений используется scope_id (channel_id после connect)
        path = f"/v2/origin/custom/{self.channel_id}"
        method = "POST"
        content_type = CONTENT_TYPE_JSON
        date = formatdate(timeval=None, localtime=False, usegmt=True)

        payload = {
            "account_id": self.account_id,
            "conversation_id": conversation_id,
            "event_type": "message_status_updated",
            "message": {
                "id": message_id,
                "status": status,
            },
        }

        import json

        body = json.dumps(payload)

        signature, content_md5 = self._generate_signature(method, path, body, content_type, date)

        headers = {
            "Date": date,
            "Content-Type": content_type,
            "Content-MD5": content_md5,
            "X-Signature": signature,
        }

        try:
            response = await client.post(f"{self.base_url}{path}", content=body, headers=headers)
            response.raise_for_status()

            result = response.json() if response.text else {}
            logger.info(f"Статус сообщения {message_id} обновлен на {status}")
            return result

        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"Не удалось обновить статус сообщения (message_id={message_id}): " f"{e.response.status_code} - {e.response.text[:200]}",
                request=e.request,
                response=e.response,
            ) from e


def get_amocrm_chat_client(
    channel_id: Optional[str] = None,
    secret_key: Optional[str] = None,
    account_id: Optional[str] = None,
) -> AmoCRMChatClient:
    """
    Фабричная функция для создания клиента AmoCRM Chat API (singleton)

    Возвращает существующий клиент из кеша или создает новый.

    Args:
        channel_id: ID канала (для connect) или scope_id (для send_message)
        secret_key: Секретный ключ интеграции
        account_id: amojo_id аккаунта AmoCRM (опционален для connect)
    """
    if not channel_id or not secret_key:
        raise ValueError("Необходимо указать channel_id и secret_key для Chat API")

    # Создаем ключ для кеша
    cache_key = (channel_id, secret_key, account_id or "")

    # Проверяем наличие клиента в кеше
    if cache_key not in _chat_client_cache:
        _chat_client_cache[cache_key] = AmoCRMChatClient(
            channel_id=channel_id,
            secret_key=secret_key,
            account_id=account_id,
        )
        logger.info(f"Создан новый singleton клиент AmoCRM Chat для channel_id: {channel_id}")

    return _chat_client_cache[cache_key]
