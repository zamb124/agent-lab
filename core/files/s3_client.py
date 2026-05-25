"""
S3 клиент для работы с объектным хранилищем.
Поддерживает AWS S3 и совместимые сервисы (Yandex Object Storage, MinIO, VK Cloud).

ВАЖНО: БЕЗ try-except блоков - fail-fast подход.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import TracebackType
from urllib.parse import urlparse

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from core.config import S3BucketConfig, get_settings
from core.context import get_context
from core.files.s3_sigv4_clock import ensure_sigv4_clock_aligned_with_endpoint
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class S3ObjectMetadata:
    content_type: str
    content_length: int
    last_modified: datetime
    etag: str
    metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class S3ListedObject:
    key: str
    size: int
    last_modified: datetime
    etag: str


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
        endpoint_url: str | None = None,
        provider_name: str = "aws",
        track_files: bool = True,
        bucket_config_key: str | None = None,
    ) -> None:
        """
        Инициализация S3 клиента.

        Args:
            bucket_name: Физическое имя bucket в S3 (для вызовов API)
            access_key_id: Ключ доступа
            secret_access_key: Секретный ключ
            region_name: Регион
            endpoint_url: URL эндпоинта S3 (для совместимых сервисов)
            provider_name: Имя провайдера (aws, yandex, minio, vkcloud)
            bucket_config_key: Ключ из settings.s3.buckets для FileRecord.s3_bucket (только из фабрики)
        """
        if not bucket_name:
            raise ValueError("bucket_name не может быть пустым")
        if not access_key_id:
            raise ValueError("access_key_id не может быть пустым")
        if not secret_access_key:
            raise ValueError("secret_access_key не может быть пустым")

        self.bucket_name: str = bucket_name
        self.bucket_config_key: str | None = bucket_config_key
        self.access_key_id: str = access_key_id
        self.secret_access_key: str = secret_access_key
        self.region_name: str = region_name
        self.endpoint_url: str | None = endpoint_url
        self.provider_name: str = provider_name
        self.track_files: bool = track_files
        self._session: aioboto3.Session | None = None
        self._client: aioboto3.S3ServiceClient | None = None
        self._client_lock: asyncio.Lock | None = None
        self._minio_bucket_lock: asyncio.Lock | None = None
        self._minio_ready_buckets: set[str] = set()

    def require_bucket_config_key(self) -> str:
        """Ключ из settings.s3.buckets для поля FileRecord.s3_bucket."""
        raw = self.bucket_config_key
        if raw is None or not str(raw).strip():
            raise ValueError(
                "S3Client без bucket_config_key: используйте S3ClientFactory.create_client_for_bucket"
            )
        return str(raw).strip()

    def _s3_endpoint_should_not_use_http_proxy(self) -> bool:
        """
        Иначе botocore подставит HTTP(S)_PROXY из окружения: запрос к MinIO на
        localhost уйдёт на внешний прокси, ответ часто приходит как InvalidAccessKeyId.
        """
        if self.provider_name == "minio":
            return True
        raw = self.endpoint_url
        if raw is None or raw == "":
            return False
        host = urlparse(raw.strip()).hostname
        if host is None:
            return False
        return host in ("localhost", "127.0.0.1", "::1", "[::1]")

    def _botocore_client_config(self) -> Config | None:
        disable_http_proxy = self._s3_endpoint_should_not_use_http_proxy()
        if self.provider_name == "vkcloud" and disable_http_proxy:
            proxies: dict[str, str] = {}
            return Config(signature_version="s3", proxies=proxies)
        if self.provider_name == "vkcloud":
            return Config(signature_version="s3")
        if disable_http_proxy:
            proxies = {}
            return Config(proxies=proxies)
        return None

    def _get_client_lock(self) -> asyncio.Lock:
        """Получает или создает лок для клиента"""
        if self._client_lock is None:
            self._client_lock = asyncio.Lock()
        return self._client_lock

    async def _get_client(self) -> aioboto3.S3ServiceClient:
        """Получает или создает S3 клиент (потокобезопасно)"""
        if self._client is None:
            lock = self._get_client_lock()
            async with lock:
                if self._client is None:
                    if self._session is None:
                        self._session = aioboto3.Session()

                    session = self._session
                    bc = self._botocore_client_config()
                    if bc is None:
                        self._client = await session.client(
                            "s3",
                            endpoint_url=self.endpoint_url,
                            aws_access_key_id=self.access_key_id,
                            aws_secret_access_key=self.secret_access_key,
                            region_name=self.region_name,
                        ).__aenter__()
                    else:
                        self._client = await session.client(
                            "s3",
                            endpoint_url=self.endpoint_url,
                            aws_access_key_id=self.access_key_id,
                            aws_secret_access_key=self.secret_access_key,
                            region_name=self.region_name,
                            config=bc,
                        ).__aenter__()

        return self._client

    async def _ensure_minio_bucket_exists(self, bucket: str) -> None:
        """
        MinIO не создаёт bucket при первом PutObject. Имя берётся только из конфига
        (self.bucket_name / аргумент), без захардкоженных строк в коде.
        Облачные S3 (Selectel, AWS) bucket создаёт администратор — не трогаем.
        """
        if self.provider_name != "minio":
            return
        if bucket in self._minio_ready_buckets:
            return
        if self._minio_bucket_lock is None:
            self._minio_bucket_lock = asyncio.Lock()
        async with self._minio_bucket_lock:
            if bucket in self._minio_ready_buckets:
                return
            client = await self._get_client()
            try:
                await client.head_bucket(Bucket=bucket)
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                status = exc.response["ResponseMetadata"]["HTTPStatusCode"]
                missing = code in ("404", "NoSuchBucket") or status == 404
                if not missing:
                    raise
                try:
                    await client.create_bucket(Bucket=bucket)
                    logger.info("S3 MinIO: создан bucket %s", bucket)
                except ClientError as create_exc:
                    ccode = create_exc.response["Error"]["Code"]
                    if ccode not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                        raise
            self._minio_ready_buckets.add(bucket)

    async def close(self) -> None:
        """Закрывает соединения клиента"""
        lock = self._get_client_lock()
        async with lock:
            client = self._client
            if client is not None:
                await client.__aexit__(None, None, None)
                self._client = None
                self._session = None

    async def __aenter__(self) -> S3Client:
        """Асинхронный контекстный менеджер"""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Закрытие при выходе из контекста"""
        await self.close()

    async def upload_file(
        self,
        file_path: str | Path,
        key: str,
        bucket: str | None = None,
        metadata: dict[str, str] | None = None,
        content_type: str | None = None,
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
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket не указан")

        await self._ensure_minio_bucket_exists(target_bucket)
        client = await self._get_client()

        extra_args: aioboto3.S3UploadExtraArgs = {}
        if metadata is not None:
            extra_args["Metadata"] = metadata
        if content_type is not None:
            if content_type == "":
                raise ValueError("content_type не может быть пустым")
            extra_args["ContentType"] = content_type
        if public:
            extra_args["ACL"] = "public-read"

        await client.upload_file(
            str(file_path),
            target_bucket,
            key,
            ExtraArgs=extra_args if extra_args else None,
        )

        logger.info(f"Файл загружен в S3: {target_bucket}/{key}")
        return True

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        bucket: str | None = None,
        metadata: dict[str, str] | None = None,
        content_type: str | None = None,
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
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket не указан")

        await self._ensure_minio_bucket_exists(target_bucket)
        client = await self._get_client()

        put_object_request: aioboto3.S3PutObjectRequest = {
            "Bucket": target_bucket,
            "Key": key,
            "Body": data,
        }
        if metadata is not None:
            put_object_request["Metadata"] = metadata
        if content_type is not None:
            if content_type == "":
                raise ValueError("content_type не может быть пустым")
            put_object_request["ContentType"] = content_type
        if public:
            put_object_request["ACL"] = "public-read"

        await client.put_object(**put_object_request)

        logger.info(f"Данные загружены в S3: {target_bucket}/{key} ({len(data)} байт)")
        return True

    async def download_file(
        self,
        key: str,
        file_path: str | Path,
        bucket: str | None = None,
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
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        await client.download_file(target_bucket, key, str(file_path))

        logger.info(f"Файл скачан из S3: {target_bucket}/{key} -> {file_path}")
        return True

    async def download_bytes(
        self,
        key: str,
        bucket: str | None = None,
    ) -> bytes:
        """
        Скачивает данные из S3 в память.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Returns:
            Данные файла
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        response = await client.get_object(Bucket=target_bucket, Key=key)
        data = await response["Body"].read()

        logger.info(f"Данные скачаны из S3: {target_bucket}/{key} ({len(data)} байт)")
        return data

    async def open_object_body(
        self,
        key: str,
        bucket: str | None = None,
        byte_range: str | None = None,
    ) -> aioboto3.S3ObjectBody:
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket не указан")

        client = await self._get_client()
        if byte_range is None:
            response = await client.get_object(Bucket=target_bucket, Key=key)
        else:
            response = await client.get_object(Bucket=target_bucket, Key=key, Range=byte_range)
        return response["Body"]

    async def delete_file(
        self,
        key: str,
        bucket: str | None = None,
    ) -> bool:
        """
        Удаляет файл из S3.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Returns:
            True если удаление успешно
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        await client.delete_object(Bucket=target_bucket, Key=key)

        logger.info(f"Файл удален из S3: {target_bucket}/{key}")
        return True

    async def file_exists(
        self,
        key: str,
        bucket: str | None = None,
    ) -> bool:
        """
        Проверяет существование файла в S3.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Returns:
            True если файл существует
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        _ = await client.head_object(Bucket=target_bucket, Key=key)
        return True

    async def get_object_metadata(
        self,
        key: str,
        bucket: str | None = None,
    ) -> S3ObjectMetadata:
        """
        Получает метаданные объекта из S3.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Returns:
            Метаданные объекта
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        response = await client.head_object(Bucket=target_bucket, Key=key)

        return S3ObjectMetadata(
            content_type=response["ContentType"],
            content_length=response["ContentLength"],
            last_modified=response["LastModified"],
            etag=response["ETag"].strip('"'),
            metadata=response["Metadata"],
        )

    async def get_presigned_url(
        self,
        key: str,
        bucket: str | None = None,
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
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        params: aioboto3.S3ObjectRequest = {"Bucket": target_bucket, "Key": key}
        url = await client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expiration,
        )

        return url

    def get_public_url(
        self,
        key: str,
        bucket: str | None = None,
    ) -> str:
        """
        Генерирует публичный URL для файла.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Returns:
            Публичный URL
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket не указан")

        if self.endpoint_url:
            return f"{self.endpoint_url}/{target_bucket}/{key}"
        return f"https://{target_bucket}.s3.{self.region_name}.amazonaws.com/{key}"

    async def list_objects(
        self,
        prefix: str = "",
        max_keys: int = 1000,
        bucket: str | None = None,
        start_after: str | None = None,
    ) -> list[S3ListedObject]:
        """
        Список объектов в bucket с указанным префиксом.

        Args:
            prefix: Префикс для фильтрации объектов
            max_keys: Максимальное количество объектов
            bucket: Имя bucket (если не указан, используется дефолтный)
            start_after: S3 StartAfter — только ключи лексикографически после этого (инкрементальный обход)

        Returns:
            Список объектов с ключами и метаданными
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        if start_after is not None and start_after != "":
            response = await client.list_objects_v2(
                Bucket=target_bucket,
                Prefix=prefix,
                MaxKeys=max_keys,
                StartAfter=start_after,
            )
        else:
            response = await client.list_objects_v2(
                Bucket=target_bucket,
                Prefix=prefix,
                MaxKeys=max_keys,
            )

        objects: list[S3ListedObject] = []
        if "Contents" in response:
            for obj in response["Contents"]:
                objects.append(
                    S3ListedObject(
                        key=obj["Key"],
                        size=obj["Size"],
                        last_modified=obj["LastModified"],
                        etag=obj["ETag"],
                    )
                )

        return objects

    async def copy_object(
        self,
        source_key: str,
        dest_key: str,
        source_bucket: str | None = None,
        dest_bucket: str | None = None,
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
        target_source_bucket = self.bucket_name if source_bucket is None else source_bucket
        target_dest_bucket = self.bucket_name if dest_bucket is None else dest_bucket
        if target_source_bucket == "" or target_dest_bucket == "":
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        copy_source: aioboto3.S3CopySource = {"Bucket": target_source_bucket, "Key": source_key}
        await client.copy_object(
            CopySource=copy_source,
            Bucket=target_dest_bucket,
            Key=dest_key,
        )

        logger.info(
            f"Объект скопирован: {target_source_bucket}/{source_key} -> {target_dest_bucket}/{dest_key}"
        )
        return True

    async def generate_presigned_url(
        self,
        key: str,
        bucket: str | None = None,
        expiration: int = 3600,
        method: aioboto3.S3PresignedMethod = "get_object",
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
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        params: aioboto3.S3ObjectRequest = {"Bucket": target_bucket, "Key": key}
        url = await client.generate_presigned_url(
            method,
            Params=params,
            ExpiresIn=expiration,
        )

        return url

class S3ClientFactory:
    """Фабрика для создания S3 клиентов"""

    @staticmethod
    def create_client(
        bucket_config: S3BucketConfig,
        physical_bucket_name: str,
        *,
        bucket_config_key: str,
    ) -> S3Client:
        """
        Создает S3 клиент из конфигурации.

        Args:
            bucket_config: Конфигурация bucket
            physical_bucket_name: Имя bucket в S3 (put_object/get_object)
            bucket_config_key: Ключ в settings.s3.buckets — пишется в FileRecord.s3_bucket

        Returns:
            Настроенный S3Client
        """
        if not bucket_config.enabled:
            raise ValueError(f"Bucket {bucket_config_key} отключен в конфигурации")

        if not bucket_config.access_key_id:
            raise ValueError(f"access_key_id не настроен для bucket {bucket_config_key}")

        if not bucket_config.secret_access_key:
            raise ValueError(f"secret_access_key не настроен для bucket {bucket_config_key}")

        ensure_sigv4_clock_aligned_with_endpoint(bucket_config.endpoint_url)

        return S3Client(
            bucket_name=physical_bucket_name,
            access_key_id=bucket_config.access_key_id,
            secret_access_key=bucket_config.secret_access_key,
            region_name=bucket_config.region_name,
            endpoint_url=bucket_config.endpoint_url,
            provider_name=bucket_config.provider,
            bucket_config_key=bucket_config_key,
        )

    @staticmethod
    def create_client_for_bucket(bucket_name: str) -> S3Client:
        """
        Создает S3 клиент для указанного bucket из settings.

        Args:
            bucket_name: Ключ bucket в конфигурации (не обязательно реальное имя bucket)

        Returns:
            Настроенный S3Client
        """
        settings = get_settings()

        if not settings.s3.enabled:
            raise ValueError("S3 отключен в конфигурации")

        if bucket_name not in settings.s3.buckets:
            raise ValueError(f"Bucket {bucket_name} не найден в конфигурации")

        bucket_config = settings.s3.buckets[bucket_name]
        real_bucket_name = bucket_config.bucket_name
        if real_bucket_name is None or real_bucket_name == "":
            real_bucket_name = bucket_name
        return S3ClientFactory.create_client(
            bucket_config,
            real_bucket_name,
            bucket_config_key=bucket_name,
        )

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

def build_s3_key_for_company(company_slug: str, relative_path: str) -> str:
    """
    Строит S3 ключ с префиксом компании.

    Args:
        company_slug: Slug компании (subdomain или company_id)
        relative_path: Относительный путь (например "rag/namespace/file.pdf")

    Returns:
        Полный ключ: "company_slug/relative_path"

    Example:
        >>> build_s3_key_for_company("system", "rag/ns1/doc.pdf")
        "system/rag/ns1/doc.pdf"
    """
    return f"{company_slug}/{relative_path.lstrip('/')}"

def build_s3_key_from_context(relative_path: str) -> str:
    """
    Строит S3 ключ из текущего контекста запроса.

    Автоматически определяет company_slug из активной компании в контексте.

    Args:
        relative_path: Относительный путь

    Returns:
        Полный ключ с префиксом компании из контекста

    Raises:
        ValueError: Если контекст или компания не найдены

    Example:
        >>> # При активной компании "system"
        >>> build_s3_key_from_context("rag/ns1/doc.pdf")
        "system/rag/ns1/doc.pdf"
    """
    context = get_context()
    if context is None:
        raise ValueError("Контекст не найден для построения S3 ключа")
    if not context.active_company:
        raise ValueError("Компания не найдена в контексте для построения S3 ключа")

    company_slug = context.active_company.subdomain or context.active_company.company_id
    if not company_slug:
        raise ValueError(f"Company subdomain и company_id пусты: {context.active_company}")

    return build_s3_key_for_company(company_slug, relative_path)
