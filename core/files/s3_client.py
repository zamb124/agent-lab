"""
S3 клиент для работы с объектным хранилищем.
Поддерживает AWS S3 и совместимые сервисы (Yandex Object Storage, MinIO, VK Cloud).

ВАЖНО: БЕЗ try-except блоков - fail-fast подход.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Union, List
from pathlib import Path
import aioboto3
from botocore.config import Config

from core.config import get_settings, S3BucketConfig

logger = logging.getLogger(__name__)


class S3Client:
    """
    Асинхронный клиент для работы с S3-совместимыми хранилищами.
    """

    def __init__(
        self,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
        region_name: str = "us-east-1",
        endpoint_url: Optional[str] = None,
        provider_name: str = "aws",
        track_files: bool = True,
    ):
        """
        Инициализация S3 клиента.

        Args:
            bucket_name: Имя bucket
            access_key_id: Ключ доступа
            secret_access_key: Секретный ключ
            region_name: Регион
            endpoint_url: URL эндпоинта S3 (для совместимых сервисов)
            provider_name: Имя провайдера (aws, yandex, minio, vkcloud)
        """
        if not bucket_name:
            raise ValueError("bucket_name не может быть пустым")
        if not access_key_id:
            raise ValueError("access_key_id не может быть пустым")
        if not secret_access_key:
            raise ValueError("secret_access_key не может быть пустым")

        self.bucket_name = bucket_name
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self.provider_name = provider_name
        self.track_files = track_files
        self._session = None
        self._client = None
        self._client_lock: Optional[asyncio.Lock] = None

    def _get_client_lock(self) -> asyncio.Lock:
        """Получает или создает лок для клиента"""
        if self._client_lock is None:
            self._client_lock = asyncio.Lock()
        return self._client_lock

    async def _get_client(self):
        """Получает или создает S3 клиент (потокобезопасно)"""
        if self._client is None:
            lock = self._get_client_lock()
            async with lock:
                if self._client is None:
                    if self._session is None:
                        self._session = aioboto3.Session()

                    client_config = {}
                    if self.provider_name == "vkcloud":
                        client_config["config"] = Config(signature_version="s3")

                    self._client = await self._session.client(
                        "s3",
                        endpoint_url=self.endpoint_url,
                        aws_access_key_id=self.access_key_id,
                        aws_secret_access_key=self.secret_access_key,
                        region_name=self.region_name,
                        **client_config,
                    ).__aenter__()

        return self._client

    async def close(self):
        """Закрывает соединения клиента"""
        lock = self._get_client_lock()
        async with lock:
            if self._client:
                await self._client.__aexit__(None, None, None)
                self._client = None
                self._session = None

    async def __aenter__(self):
        """Асинхронный контекстный менеджер"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Закрытие при выходе из контекста"""
        await self.close()

    async def upload_file(
        self,
        file_path: Union[str, Path],
        key: str,
        bucket: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        public: bool = False,
    ) -> bool:
        """
        Загружает файл в S3.

        Args:
            file_path: Путь к файлу для загрузки
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)
            metadata: Метаданные объекта
            content_type: MIME тип файла
            public: Сделать файл публичным (ACL: public-read)

        Returns:
            True если загрузка успешна
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        extra_args = {}
        if metadata:
            extra_args["Metadata"] = metadata
        if content_type:
            extra_args["ContentType"] = content_type
        if public:
            extra_args["ACL"] = "public-read"

        await client.upload_file(
            str(file_path),
            bucket,
            key,
            ExtraArgs=extra_args if extra_args else None,
        )

        logger.info(f"Файл загружен в S3: {bucket}/{key}")
        return True

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        bucket: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        public: bool = False,
    ) -> bool:
        """
        Загружает данные из памяти в S3.

        Args:
            data: Данные для загрузки
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)
            metadata: Метаданные объекта
            content_type: MIME тип
            public: Сделать файл публичным

        Returns:
            True если загрузка успешна
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        extra_args = {}
        if metadata:
            extra_args["Metadata"] = metadata
        if content_type:
            extra_args["ContentType"] = content_type
        if public:
            extra_args["ACL"] = "public-read"

        await client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            **extra_args,
        )

        logger.info(f"Данные загружены в S3: {bucket}/{key} ({len(data)} байт)")
        return True

    async def download_file(
        self,
        key: str,
        file_path: Union[str, Path],
        bucket: Optional[str] = None,
    ) -> bool:
        """
        Скачивает файл из S3.

        Args:
            key: Ключ объекта в S3
            file_path: Путь для сохранения файла
            bucket: Имя bucket (если не указан, используется дефолтный)

        Returns:
            True если скачивание успешно
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        await client.download_file(bucket, key, str(file_path))

        logger.info(f"Файл скачан из S3: {bucket}/{key} -> {file_path}")
        return True

    async def download_bytes(
        self,
        key: str,
        bucket: Optional[str] = None,
    ) -> bytes:
        """
        Скачивает данные из S3 в память.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Returns:
            Данные файла
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        response = await client.get_object(Bucket=bucket, Key=key)
        data = await response["Body"].read()

        logger.info(f"Данные скачаны из S3: {bucket}/{key} ({len(data)} байт)")
        return data

    async def delete_file(
        self,
        key: str,
        bucket: Optional[str] = None,
    ) -> bool:
        """
        Удаляет файл из S3.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Returns:
            True если удаление успешно
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        await client.delete_object(Bucket=bucket, Key=key)

        logger.info(f"Файл удален из S3: {bucket}/{key}")
        return True

    async def delete_object(self, key: str, bucket: Optional[str] = None) -> bool:
        """Алиас для delete_file (совместимость с тестами)"""
        return await self.delete_file(key, bucket)

    async def file_exists(
        self,
        key: str,
        bucket: Optional[str] = None,
    ) -> bool:
        """
        Проверяет существование файла в S3.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Returns:
            True если файл существует
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        await client.head_object(Bucket=bucket, Key=key)
        return True

    async def get_object_metadata(
        self,
        key: str,
        bucket: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Получает метаданные объекта из S3.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Returns:
            Словарь с метаданными объекта
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        response = await client.head_object(Bucket=bucket, Key=key)
        
        metadata = {
            "content_type": response.get("ContentType"),
            "content_length": response.get("ContentLength"),
            "last_modified": response.get("LastModified"),
            "etag": response.get("ETag", "").strip('"'),
            "metadata": response.get("Metadata", {}),
        }
        
        return metadata

    async def get_presigned_url(
        self,
        key: str,
        bucket: Optional[str] = None,
        expiration: int = 3600,
    ) -> str:
        """
        Генерирует временный URL для доступа к файлу.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)
            expiration: Время жизни URL в секундах

        Returns:
            Временный URL
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        url = await client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiration,
        )

        return url

    def get_public_url(
        self,
        key: str,
        bucket: Optional[str] = None,
    ) -> str:
        """
        Генерирует публичный URL для файла.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Returns:
            Публичный URL
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        if self.endpoint_url:
            return f"{self.endpoint_url}/{bucket}/{key}"
        else:
            return f"https://{bucket}.s3.{self.region_name}.amazonaws.com/{key}"

    async def object_exists(self, key: str, bucket: Optional[str] = None) -> bool:
        """Алиас для file_exists (совместимость с тестами)"""
        return await self.file_exists(key, bucket)

    async def list_objects(
        self,
        prefix: str = "",
        max_keys: int = 1000,
        bucket: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Список объектов в bucket с указанным префиксом.

        Args:
            prefix: Префикс для фильтрации объектов
            max_keys: Максимальное количество объектов
            bucket: Имя bucket (если не указан, используется дефолтный)

        Returns:
            Список объектов с ключами и метаданными
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        response = await client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            MaxKeys=max_keys,
        )

        objects = []
        if "Contents" in response:
            for obj in response["Contents"]:
                objects.append({
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"],
                    "etag": obj["ETag"],
                })

        return objects

    async def copy_object(
        self,
        source_key: str,
        dest_key: str,
        source_bucket: Optional[str] = None,
        dest_bucket: Optional[str] = None,
    ) -> bool:
        """
        Копирует объект в S3.

        Args:
            source_key: Ключ исходного объекта
            dest_key: Ключ целевого объекта
            source_bucket: Имя исходного bucket (если не указан, используется дефолтный)
            dest_bucket: Имя целевого bucket (если не указан, используется дефолтный)

        Returns:
            True если копирование успешно
        """
        source_bucket = source_bucket or self.bucket_name
        dest_bucket = dest_bucket or self.bucket_name
        if not source_bucket or not dest_bucket:
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        copy_source = {"Bucket": source_bucket, "Key": source_key}
        await client.copy_object(
            CopySource=copy_source,
            Bucket=dest_bucket,
            Key=dest_key,
        )

        logger.info(f"Объект скопирован: {source_bucket}/{source_key} -> {dest_bucket}/{dest_key}")
        return True

    async def generate_presigned_url(
        self,
        key: str,
        bucket: Optional[str] = None,
        expiration: int = 3600,
        method: str = "get_object",
    ) -> str:
        """
        Генерирует presigned URL с указанным методом.
        
        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)
            expiration: Время жизни URL в секундах
            method: HTTP метод ('get_object', 'put_object')
            
        Returns:
            Временный URL
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        url = await client.generate_presigned_url(
            method,
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiration,
        )

        return url


class S3ClientFactory:
    """Фабрика для создания S3 клиентов"""

    @staticmethod
    def create_client(bucket_config: S3BucketConfig, bucket_name: str) -> S3Client:
        """
        Создает S3 клиент из конфигурации.

        Args:
            bucket_config: Конфигурация bucket
            bucket_name: Имя bucket

        Returns:
            Настроенный S3Client
        """
        if not bucket_config.enabled:
            raise ValueError(f"Bucket {bucket_name} отключен в конфигурации")

        if not bucket_config.access_key_id:
            raise ValueError(f"access_key_id не настроен для bucket {bucket_name}")

        if not bucket_config.secret_access_key:
            raise ValueError(f"secret_access_key не настроен для bucket {bucket_name}")

        return S3Client(
            bucket_name=bucket_name,
            access_key_id=bucket_config.access_key_id,
            secret_access_key=bucket_config.secret_access_key,
            region_name=bucket_config.region_name,
            endpoint_url=bucket_config.endpoint_url,
            provider_name=bucket_config.provider,
        )

    @staticmethod
    def create_client_for_bucket(bucket_name: str) -> S3Client:
        """
        Создает S3 клиент для указанного bucket из settings.

        Args:
            bucket_name: Имя bucket

        Returns:
            Настроенный S3Client
        """
        settings = get_settings()

        if not settings.s3.enabled:
            raise ValueError("S3 отключен в конфигурации")

        if bucket_name not in settings.s3.buckets:
            raise ValueError(f"Bucket {bucket_name} не найден в конфигурации")

        bucket_config = settings.s3.buckets[bucket_name]
        return S3ClientFactory.create_client(bucket_config, bucket_name)

    @staticmethod
    def create_default_client() -> S3Client:
        """
        Создает S3 клиент для дефолтного bucket из settings.

        Returns:
            Настроенный S3Client
        """
        settings = get_settings()

        if not settings.s3.enabled:
            raise ValueError("S3 отключен в конфигурации")

        if not settings.s3.default_bucket:
            raise ValueError("Дефолтный bucket не настроен")

        return S3ClientFactory.create_client_for_bucket(settings.s3.default_bucket)


_default_s3_client: Optional[S3Client] = None
_default_s3_client_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    """Получает или создает лок для глобального S3 клиента"""
    global _default_s3_client_lock
    if _default_s3_client_lock is None:
        _default_s3_client_lock = asyncio.Lock()
    return _default_s3_client_lock


async def get_default_s3_client() -> Optional[S3Client]:
    """
    Получает дефолтный S3 клиент на основе конфигурации.
    Потокобезопасно создает клиент при первом обращении.

    Returns:
        S3 клиент или None если не настроен
    """
    global _default_s3_client

    if _default_s3_client is None:
        lock = _get_lock()
        async with lock:
            if _default_s3_client is None:
                settings = get_settings()
                if (
                    hasattr(settings, "s3")
                    and settings.s3.enabled
                    and settings.s3.default_bucket
                ):
                    _default_s3_client = S3ClientFactory.create_client_for_bucket(
                        settings.s3.default_bucket
                    )
                    logger.info(
                        f"✅ Инициализирован дефолтный S3 клиент для бакета: {settings.s3.default_bucket}"
                    )
                else:
                    logger.info("ℹ️ S3 не настроен в конфигурации")

    return _default_s3_client


async def close_default_s3_client():
    """Закрывает дефолтный S3 клиент"""
    global _default_s3_client
    if _default_s3_client:
        await _default_s3_client.close()
        _default_s3_client = None

