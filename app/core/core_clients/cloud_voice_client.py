"""
Cloud Voice клиент для работы с VK Cloud Voice API.
Поддерживает распознавание аудиофайлов, потокового аудио и синтез речи.

СИСТЕМА ТОКЕНОВ:
- Токены сохраняются в БД (Storage) с ключом cloud_voice_token:{client_id}
- При первом запросе получаем новую пару access_token + refresh_token
- При последующих запросах используем сохраненный access_token
- Если access_token истек, используем refresh_token для получения нового
- Если refresh_token истек (>30 дней), получаем новую пару через client_credentials
- Это решает проблему лимита "до 25 активных refresh_token" из документации VK Cloud
"""

import logging
import time
from typing import Optional, Dict, Any, List, Union, AsyncGenerator
from pathlib import Path
import httpx
from datetime import datetime, timedelta, timezone

from ..config import settings
from ..storage import Storage
from ...models.core_models import CloudVoiceTokenConfig

logger = logging.getLogger(__name__)




class CloudVoiceClient:
    """
    Клиент для работы с VK Cloud Voice API.
    Поддерживает распознавание аудио и синтез речи.
    """

    def __init__(
        self,
        client_id: str,
        secret_key: str,
        auth_url: str = "https://mcs.mail.ru/auth/oauth/v1/token",
        asr_url: str = "https://voice.mcs.mail.ru/asr",
        asr_stream_url: str = "https://voice.mcs.mail.ru/asr_stream",
        tts_url: str = "https://voice.mcs.mail.ru/tts",
        timeout: int = 30,
    ):
        """
        Инициализация Cloud Voice клиента.

        Args:
            client_id: ID клиента
            secret_key: Секретный ключ
            auth_url: URL для получения токена
            asr_url: URL для распознавания аудиофайлов
            asr_stream_url: URL для потокового распознавания
            tts_url: URL для синтеза речи
            timeout: Таймаут запросов
        """
        self.client_id = client_id
        self.secret_key = secret_key
        self.auth_url = auth_url
        self.asr_url = asr_url
        self.asr_stream_url = asr_stream_url
        self.tts_url = tts_url
        self.timeout = timeout
        self._token_config: Optional[CloudVoiceTokenConfig] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._storage = Storage()
        self._token_key = f"cloud_voice_token:{self.client_id}"

    async def _get_client(self) -> httpx.AsyncClient:
        """Получает или создает HTTP клиент"""
        if self._client is None:
            # Временно отключаем проверку SSL из-за проблем с сертификатом mcs.mail.ru
            self._client = httpx.AsyncClient(timeout=self.timeout, verify=False)
        return self._client

    async def close(self):
        """Закрывает HTTP клиент"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def clear_token(self):
        """Принудительно очищает сохраненный токен"""
        try:
            await self._storage.delete(self._token_key)
            self._token_config = None
            logger.info("✅ Токен Cloud Voice удален из БД")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка удаления токена из БД: {e}")
    
    async def force_refresh_token(self):
        """Принудительно обновляет токен (игнорируя кэш)"""
        self._token_config = None
        await self._refresh_token()
        logger.info("✅ Токен Cloud Voice принудительно обновлен")

    async def __aenter__(self):
        """Асинхронный контекстный менеджер"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Закрытие при выходе из контекста"""
        await self.close()

    async def _load_token_from_db(self) -> Optional[CloudVoiceTokenConfig]:
        """Загружает токен из БД"""
        try:
            token_data = await self._storage.get(self._token_key)
            if token_data:
                return CloudVoiceTokenConfig.model_validate_json(token_data)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка загрузки токена из БД: {e}")
        return None
    
    async def _save_token_to_db(self, token_config: CloudVoiceTokenConfig):
        """Сохраняет токен в БД"""
        try:
            token_config.updated_at = datetime.now(timezone.utc)
            await self._storage.set(self._token_key, token_config.model_dump_json())
            logger.info("✅ Токен Cloud Voice сохранен в БД")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения токена в БД: {e}")
    
    async def _get_access_token(self) -> str:
        """
        Получает или обновляет access token.
        
        Returns:
            Актуальный access token
        """
        # Загружаем токен из БД если еще не загружен
        if self._token_config is None:
            self._token_config = await self._load_token_from_db()
        
        # Если токена нет или он истек - обновляем
        if self._token_config is None or self._token_config.is_expired():
            await self._refresh_token()
        
        return self._token_config.access_token

    async def _refresh_token(self):
        """Обновляет токен доступа"""
        client = await self._get_client()
        
        # Проверяем есть ли сохраненный refresh_token и не истек ли он
        use_refresh_token = (
            self._token_config is not None 
            and not self._token_config.is_refresh_expired()
            and self._token_config.refresh_token
        )
        
        if use_refresh_token:
            # Используем refresh token для получения нового access token
            payload = {
                "client_id": self.client_id,
                "refresh_token": self._token_config.refresh_token,
                "grant_type": "refresh_token"
            }
            logger.info("🔄 Используем сохраненный refresh_token для обновления")
        else:
            # Получаем новые токены через client_credentials
            payload = {
                "client_id": self.client_id,
                "client_secret": self.secret_key,
                "grant_type": "client_credentials"
            }
            logger.info("🆕 Получаем новую пару токенов через client_credentials")

        try:
            response = await client.post(
                self.auth_url,
                headers={"Content-Type": "application/json"},
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Создаем новую конфигурацию токена
            expires_in = int(data["expired_in"])
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)  # 60 сек запас
            
            self._token_config = CloudVoiceTokenConfig(
                client_id=self.client_id,
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=expires_at,
                created_at=self._token_config.created_at if use_refresh_token and self._token_config else datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            
            # Сохраняем в БД
            await self._save_token_to_db(self._token_config)
            
            logger.info("✅ Cloud Voice токен успешно получен/обновлен и сохранен в БД")
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Ошибка получения токена Cloud Voice: {e.response.status_code} - {e.response.text}")
            
            # Если refresh_token истек, пробуем получить новую пару токенов
            if e.response.status_code == 400 and use_refresh_token:
                logger.warning("⚠️ Refresh token истек, получаем новую пару токенов")
                self._token_config = None  # Сбрасываем токен
                await self._refresh_token()  # Рекурсивный вызов для получения новых токенов
                return
            
            raise
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при получении токена: {e}")
            raise

    async def recognize_audio_file(
        self, 
        audio_data: bytes, 
        content_type: str = "audio/wave"
    ) -> Dict[str, Any]:
        """
        Распознавание аудиофайла.

        Args:
            audio_data: Данные аудиофайла
            content_type: MIME тип аудио (audio/wave, audio/ogg)

        Returns:
            Результат распознавания
        """
        if len(audio_data) > 20 * 1024 * 1024:  # 20 MB
            raise ValueError("Размер аудиофайла превышает 20 МБ")

        client = await self._get_client()
        token = await self._get_access_token()

        try:
            response = await client.post(
                self.asr_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": content_type
                },
                content=audio_data
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"✅ Аудиофайл распознан (qid: {result.get('qid', 'unknown')})")
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Ошибка распознавания аудиофайла: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при распознавании аудиофайла: {e}")
            raise

    async def recognize_audio_file_from_path(
        self, 
        file_path: Union[str, Path], 
        content_type: str = "audio/wave"
    ) -> Dict[str, Any]:
        """
        Распознавание аудиофайла по пути.

        Args:
            file_path: Путь к аудиофайлу
            content_type: MIME тип аудио

        Returns:
            Результат распознавания
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Аудиофайл не найден: {file_path}")

        with open(file_path, "rb") as f:
            audio_data = f.read()

        return await self.recognize_audio_file(audio_data, content_type)

    async def create_stream_task(self) -> Dict[str, str]:
        """
        Создает задачу для потокового распознавания.

        Returns:
            task_id и task_token для потокового распознавания
        """
        client = await self._get_client()
        token = await self._get_access_token()

        try:
            response = await client.post(
                f"{self.asr_stream_url}/create_task",
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            
            data = response.json()
            result = data["result"]
            
            logger.info(f"✅ Задача потокового распознавания создана (task_id: {result['task_id']})")
            return {
                "task_id": result["task_id"],
                "task_token": result["task_token"]
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Ошибка создания задачи потокового распознавания: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при создании задачи: {e}")
            raise

    async def add_audio_chunk(
        self,
        task_id: str,
        task_token: str,
        chunk_num: int,
        chunk_data: bytes,
        content_type: str = "audio/wave"
    ) -> Dict[str, Any]:
        """
        Добавляет аудио чанк к задаче потокового распознавания.

        Args:
            task_id: ID задачи
            task_token: Токен задачи
            chunk_num: Номер чанка (начиная с 1)
            chunk_data: Данные аудио чанка
            content_type: MIME тип аудио

        Returns:
            Промежуточный результат распознавания
        """
        if len(chunk_data) > 32100:  # 32100 bytes
            raise ValueError("Размер чанка превышает 32100 байт")

        client = await self._get_client()

        try:
            response = await client.post(
                f"{self.asr_stream_url}/add_chunk",
                params={
                    "task_id": task_id,
                    "chunk_num": chunk_num
                },
                headers={
                    "Authorization": f"Bearer {task_token}",
                    "Content-Type": content_type
                },
                content=chunk_data
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"✅ Чанк {chunk_num} добавлен к задаче {task_id}")
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Ошибка добавления чанка: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при добавлении чанка: {e}")
            raise

    async def get_stream_result(self, task_id: str, task_token: str) -> Dict[str, Any]:
        """
        Получает финальный результат потокового распознавания.

        Args:
            task_id: ID задачи
            task_token: Токен задачи

        Returns:
            Финальный результат распознавания
        """
        client = await self._get_client()

        try:
            response = await client.get(
                f"{self.asr_stream_url}/get_result",
                params={"task_id": task_id},
                headers={"Authorization": f"Bearer {task_token}"}
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"✅ Получен финальный результат для задачи {task_id}")
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Ошибка получения результата: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при получении результата: {e}")
            raise

    async def synthesize_speech(
        self,
        text: str,
        model_name: str = "katherine",
        encoder: str = "pcm",
        tempo: float = 1.0
    ) -> bytes:
        """
        Синтезирует речь из текста.

        Args:
            text: Текст для синтеза
            model_name: Модель голоса (katherine, maria, pavel)
            encoder: Тип энкодера (pcm, mp3, opus)
            tempo: Скорость речи (0.75 - 1.75)

        Returns:
            Аудиоданные
        """
        if not 0.75 <= tempo <= 1.75:
            raise ValueError("Скорость речи должна быть от 0.75 до 1.75")

        client = await self._get_client()
        token = await self._get_access_token()

        params = {
            "model_name": model_name,
            "encoder": encoder,
            "tempo": tempo
        }

        try:
            response = await client.post(
                self.tts_url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                data=text
            )
            response.raise_for_status()
            
            audio_data = response.content
            logger.info(f"✅ Речь синтезирована ({len(audio_data)} байт, модель: {model_name})")
            return audio_data
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Ошибка синтеза речи: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при синтезе речи: {e}")
            raise

    async def synthesize_speech_get(
        self,
        text: str,
        model_name: str = "katherine",
        encoder: str = "pcm",
        tempo: float = 1.0
    ) -> bytes:
        """
        Синтезирует речь из текста через GET запрос.

        Args:
            text: Текст для синтеза
            model_name: Модель голоса
            encoder: Тип энкодера
            tempo: Скорость речи

        Returns:
            Аудиоданные
        """
        if not 0.75 <= tempo <= 1.75:
            raise ValueError("Скорость речи должна быть от 0.75 до 1.75")

        client = await self._get_client()
        token = await self._get_access_token()

        params = {
            "text": text,
            "model_name": model_name,
            "encoder": encoder,
            "tempo": tempo
        }

        try:
            response = await client.get(
                self.tts_url,
                headers={"Authorization": f"Bearer {token}"},
                params=params
            )
            response.raise_for_status()
            
            audio_data = response.content
            logger.info(f"✅ Речь синтезирована GET ({len(audio_data)} байт, модель: {model_name})")
            return audio_data
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Ошибка синтеза речи GET: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при синтезе речи GET: {e}")
            raise

    def get_best_recognition_text(self, recognition_result: Dict[str, Any]) -> str:
        """
        Извлекает лучший результат распознавания из ответа API.

        Args:
            recognition_result: Результат от API распознавания

        Returns:
            Лучший распознанный текст
        """
        result = recognition_result.get("result", {})
        
        # Для потокового распознавания
        if "text" in result:
            return result.get("punctuated_text", result.get("text", ""))
        
        # Для файлового распознавания
        texts = result.get("texts", [])
        if texts:
            # Берем первый результат (с максимальной confidence)
            best_text = texts[0]
            return best_text.get("punctuated_text", best_text.get("text", ""))
        
        return ""


class CloudVoiceClientFactory:
    """
    Фабрика для создания Cloud Voice клиентов на основе конфигурации.
    """

    @staticmethod
    def create_client() -> CloudVoiceClient:
        """
        Создает Cloud Voice клиент из конфигурации.

        Returns:
            Настроенный Cloud Voice клиент
        """
        if not settings.cloud_voice.enabled:
            raise ValueError("Cloud Voice отключен в конфигурации")

        if not settings.cloud_voice.client_id or not settings.cloud_voice.secret_key:
            raise ValueError("Не настроены креды для Cloud Voice")

        return CloudVoiceClient(
            client_id=settings.cloud_voice.client_id,
            secret_key=settings.cloud_voice.secret_key,
            auth_url=settings.cloud_voice.auth_url,
            asr_url=settings.cloud_voice.asr_url,
            asr_stream_url=settings.cloud_voice.asr_url.replace("/asr", "/asr_stream"),
            tts_url=settings.cloud_voice.tts_url,
            timeout=settings.cloud_voice.timeout,
        )


# Глобальный экземпляр для удобства
_default_cloud_voice_client: Optional[CloudVoiceClient] = None


async def get_default_cloud_voice_client() -> Optional[CloudVoiceClient]:
    """
    Получает дефолтный Cloud Voice клиент на основе конфигурации.

    Returns:
        Cloud Voice клиент или None если не настроен
    """
    global _default_cloud_voice_client

    if _default_cloud_voice_client is None:
        try:
            if hasattr(settings, "cloud_voice") and settings.cloud_voice.enabled:
                _default_cloud_voice_client = CloudVoiceClientFactory.create_client()
                logger.info("✅ Инициализирован дефолтный Cloud Voice клиент")
            else:
                logger.info("ℹ️ Cloud Voice не настроен в конфигурации")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Cloud Voice клиента: {e}")
            return None

    return _default_cloud_voice_client


async def close_default_cloud_voice_client():
    """Закрывает дефолтный Cloud Voice клиент"""
    global _default_cloud_voice_client

    if _default_cloud_voice_client:
        await _default_cloud_voice_client.close()
        _default_cloud_voice_client = None
        logger.info("✅ Дефолтный Cloud Voice клиент закрыт")
