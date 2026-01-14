"""
Cloud Voice клиент для работы с VK Cloud Voice API.
Поддерживает распознавание аудиофайлов и синтез речи.

АДАПТИРОВАНО: убраны зависимости от app/*, используется только core/*
"""

import logging
import json
from typing import Optional, Union
from pathlib import Path
from datetime import datetime, timedelta, timezone

from core.config import get_settings
from core.http import get_httpx_client

logger = logging.getLogger(__name__)


class CloudVoiceClient:
    """
    Клиент для работы с VK Cloud Voice API.
    Поддерживает распознавание аудио и синтез речи.
    """

    def __init__(
        self,
        storage,
        client_id: str,
        secret_key: str,
        auth_url: str = "https://mcs.mail.ru/auth/oauth/v1/token",
        asr_url: str = "https://voice.mcs.mail.ru/asr",
        tts_url: str = "https://voice.mcs.mail.ru/tts",
        timeout: int = 30,
    ):
        """
        Инициализация Cloud Voice клиента.

        Args:
            storage: Storage для сохранения токенов
            client_id: ID клиента
            secret_key: Секретный ключ
            auth_url: URL для получения токена
            asr_url: URL для распознавания аудиофайлов
            tts_url: URL для синтеза речи
            timeout: Таймаут запросов
        """
        if not client_id:
            raise ValueError("client_id не может быть пустым")
        if not secret_key:
            raise ValueError("secret_key не может быть пустым")

        self._storage = storage
        self._client_id = client_id
        self._secret_key = secret_key
        self._auth_url = auth_url
        self._asr_url = asr_url
        self._tts_url = tts_url
        self._timeout = timeout
        self._token_config = None
        self._token_key = f"cloud_voice_token:{self._client_id}"

    async def _load_token_from_storage(self) -> Optional[dict]:
        """Загружает токен из Storage"""
        token_json = await self._storage.get(self._token_key)
        if token_json:
            return json.loads(token_json)
        return None

    async def _save_token_to_storage(self, token_data: dict):
        """Сохраняет токен в Storage"""
        await self._storage.set(
            self._token_key,
            json.dumps(token_data)
        )

    async def _get_new_token(self) -> dict:
        """Получает новый токен через client_credentials"""
        logger.info("Получаем новый токен Cloud Voice...")

        async with get_httpx_client(timeout=self._timeout) as client:
            response = await client.post(
                self._auth_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._secret_key,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            token_data = response.json()

        token_data['obtained_at'] = datetime.now(timezone.utc).isoformat()
        await self._save_token_to_storage(token_data)

        logger.info("Новый токен Cloud Voice получен и сохранен")
        return token_data

    async def _get_access_token(self) -> str:
        """Получает валидный access_token"""
        token_data = await self._load_token_from_storage()

        if not token_data:
            token_data = await self._get_new_token()
            return token_data['access_token']

        obtained_at = datetime.fromisoformat(token_data['obtained_at'])
        expires_in = token_data.get('expires_in', 3600)
        
        if datetime.now(timezone.utc) - obtained_at > timedelta(seconds=expires_in - 60):
            logger.info("Токен истек, получаем новый...")
            token_data = await self._get_new_token()

        return token_data['access_token']

    async def recognize_audio(
        self,
        audio_data: Union[bytes, Path],
        language: str = "ru-RU",
    ) -> str:
        """
        Распознает аудио через VK Cloud Voice API.

        Args:
            audio_data: Аудио данные (bytes) или путь к файлу
            language: Язык распознавания

        Returns:
            Распознанный текст
        """
        if isinstance(audio_data, Path):
            with open(audio_data, 'rb') as f:
                audio_bytes = f.read()
        else:
            audio_bytes = audio_data

        access_token = await self._get_access_token()

        async with get_httpx_client(timeout=self._timeout) as client:
            response = await client.post(
                self._asr_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "audio/wave",
                },
                params={
                    "language": language,
                },
                content=audio_bytes,
            )
            response.raise_for_status()
            result = response.json()

        transcription = result.get('Text', result.get('text', ''))
        logger.info(f"Распознан текст: {transcription[:100]}...")
        
        return transcription

    async def synthesize_speech(
        self,
        text: str,
        voice: str = "maria",
        language: str = "ru-RU",
    ) -> bytes:
        """
        Синтезирует речь из текста.

        Args:
            text: Текст для синтеза
            voice: Голос (maria, dmitry, etc)
            language: Язык синтеза

        Returns:
            Аудио данные
        """
        access_token = await self._get_access_token()

        async with get_httpx_client(timeout=self._timeout) as client:
            response = await client.post(
                self._tts_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "text": text,
                    "voice": voice,
                    "language": language,
                },
            )
            response.raise_for_status()
            audio_data = response.content

        logger.info(f"Синтезирована речь: {len(audio_data)} байт")
        return audio_data


class CloudVoiceClientFactory:
    """Фабрика для создания Cloud Voice клиентов"""

    @staticmethod
    def create_client(storage) -> CloudVoiceClient:
        """Создает клиент на основе конфигурации"""
        settings = get_settings()

        if not settings.cloud_voice.enabled:
            raise ValueError("Cloud Voice не настроен в конфигурации")

        if not settings.cloud_voice.client_id:
            raise ValueError("Cloud Voice client_id не настроен")

        if not settings.cloud_voice.secret_key:
            raise ValueError("Cloud Voice secret_key не настроен")

        return CloudVoiceClient(
            storage=storage,
            client_id=settings.cloud_voice.client_id,
            secret_key=settings.cloud_voice.secret_key,
            auth_url=settings.cloud_voice.auth_url,
            asr_url=settings.cloud_voice.asr_url,
            tts_url=settings.cloud_voice.tts_url,
            timeout=settings.cloud_voice.timeout,
        )




