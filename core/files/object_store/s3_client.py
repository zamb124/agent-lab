"""
S3 клиент для работы с объектным хранилищем.
Поддерживает AWS S3 и совместимые сервисы (Yandex Object Storage, SeaweedFS, MinIO, VK Cloud).

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

from core.config import get_settings
from core.files.object_storage import PLATFORM_STORAGE_ID
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

        Аргументы:
            bucket_name: Физическое имя bucket в S3 (для вызовов API)
            access_key_id: Ключ доступа
            secret_access_key: Секретный ключ
            region_name: Регион
            endpoint_url: URL эндпоинта S3 (для совместимых сервисов)
            provider_name: Имя провайдера (aws, yandex, seaweedfs, minio, vkcloud)
            bucket_config_key: Ключ из settings.s3.buckets для FileRecord.s3_bucket (только из фабрики)
        """
        if not bucket_name:
            raise ValueError("bucket_name cannot be empty")
        if not access_key_id:
            raise ValueError("access_key_id cannot be empty")
        if not secret_access_key:
            raise ValueError("secret_access_key cannot be empty")

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
        self._bucket_lock: asyncio.Lock | None = None
        self._ready_buckets: set[str] = set()

    def require_bucket_config_key(self) -> str:
        """Ключ из settings.s3.buckets для поля FileRecord.s3_bucket."""
        raw = self.bucket_config_key
        if raw is None or not str(raw).strip():
            raise ValueError(
                "S3Client without bucket_config_key: use S3ClientFactory.create_client_for_bucket"
            )
        return str(raw).strip()

    def _s3_endpoint_should_not_use_http_proxy(self) -> bool:
        """
        Иначе botocore подставит HTTP(S)_PROXY из окружения: запрос к S3-хранилищу
        на localhost уйдёт на внешний прокси, ответ часто приходит как InvalidAccessKeyId.
        """
        if self.provider_name in ("minio", "seaweedfs"):
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

    async def _ensure_bucket_exists(self, bucket: str) -> None:
        """
        Self-hosted S3 (SeaweedFS, MinIO) не создаёт bucket при первом PutObject.
        Имя берётся только из конфига (self.bucket_name / аргумент), без
        захардкоженных строк в коде.
        Облачные S3 (Selectel, AWS) bucket создаёт администратор — не трогаем.
        """
        if self.provider_name not in ("minio", "seaweedfs"):
            return
        if bucket in self._ready_buckets:
            return
        if self._bucket_lock is None:
            self._bucket_lock = asyncio.Lock()
        async with self._bucket_lock:
            if bucket in self._ready_buckets:
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
                    logger.info("files.s3.bucket", bucket=bucket)
                except ClientError as create_exc:
                    ccode = create_exc.response["Error"]["Code"]
                    if ccode not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                        raise
            self._ready_buckets.add(bucket)

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

        Аргументы:
            file_path: Путь к файлу для загрузки
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)
            metadata: Метаданные объекта
            content_type: MIME тип файла
            public: Сделать файл публичным (ACL: public-read)

        Возвращает:
            True если загрузка успешна
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")

        await self._ensure_bucket_exists(target_bucket)
        client = await self._get_client()

        extra_args: aioboto3.S3UploadExtraArgs = {}
        if metadata is not None:
            extra_args["Metadata"] = metadata
        if content_type is not None:
            if content_type == "":
                raise ValueError("content_type cannot be empty")
            extra_args["ContentType"] = content_type
        if public:
            extra_args["ACL"] = "public-read"

        await client.upload_file(
            str(file_path),
            target_bucket,
            key,
            ExtraArgs=extra_args if extra_args else None,
        )

        logger.info("s3.file_uploaded", bucket=target_bucket, key=key)
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

        Аргументы:
            data: Данные для загрузки
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)
            metadata: Метаданные объекта
            content_type: MIME тип
            public: Сделать файл публичным

        Возвращает:
            True если загрузка успешна
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")

        await self._ensure_bucket_exists(target_bucket)
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
                raise ValueError("content_type cannot be empty")
            put_object_request["ContentType"] = content_type
        if public:
            put_object_request["ACL"] = "public-read"

        await client.put_object(**put_object_request)

        logger.info("s3.data_uploaded", bucket=target_bucket, key=key, bytes=len(data))
        return True

    async def create_multipart_upload(
        self,
        key: str,
        *,
        content_type: str,
        bucket: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")
        if content_type == "":
            raise ValueError("content_type cannot be empty")
        await self._ensure_bucket_exists(target_bucket)
        client = await self._get_client()
        params: aioboto3.S3CreateMultipartUploadRequest = {
            "Bucket": target_bucket,
            "Key": key,
            "ContentType": content_type,
        }
        if metadata is not None:
            params["Metadata"] = metadata
        response = await client.create_multipart_upload(**params)
        upload_id = response["UploadId"]
        if upload_id == "":
            raise RuntimeError("S3 create_multipart_upload did not return UploadId")
        return upload_id

    async def upload_part(
        self,
        key: str,
        *,
        upload_id: str,
        part_number: int,
        data: bytes,
        bucket: str | None = None,
    ) -> str:
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")
        if upload_id == "":
            raise ValueError("upload_id is required")
        if part_number < 1:
            raise ValueError("part_number must be >= 1")
        if len(data) == 0:
            raise ValueError("multipart upload part is empty")
        client = await self._get_client()
        response = await client.upload_part(
            Bucket=target_bucket,
            Key=key,
            UploadId=upload_id,
            PartNumber=part_number,
            Body=data,
        )
        etag = response["ETag"]
        if etag == "":
            raise RuntimeError("S3 upload_part did not return ETag")
        return etag

    async def complete_multipart_upload(
        self,
        key: str,
        *,
        upload_id: str,
        parts: list[tuple[int, str]],
        bucket: str | None = None,
    ) -> None:
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")
        if upload_id == "":
            raise ValueError("upload_id is required")
        if len(parts) == 0:
            raise ValueError("multipart complete requires at least one part")
        client = await self._get_client()
        sorted_parts = sorted(parts, key=lambda item: item[0])
        await client.complete_multipart_upload(
            Bucket=target_bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={
                "Parts": [
                    {"PartNumber": part_number, "ETag": etag}
                    for part_number, etag in sorted_parts
                ]
            },
        )

    async def abort_multipart_upload(
        self,
        key: str,
        *,
        upload_id: str,
        bucket: str | None = None,
    ) -> None:
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")
        if upload_id == "":
            raise ValueError("upload_id is required")
        client = await self._get_client()
        await client.abort_multipart_upload(
            Bucket=target_bucket,
            Key=key,
            UploadId=upload_id,
        )

    async def download_file(
        self,
        key: str,
        file_path: str | Path,
        bucket: str | None = None,
    ) -> bool:
        """
        Скачивает файл из S3.

        Аргументы:
            key: Ключ объекта в S3
            file_path: Путь для сохранения файла
            bucket: Имя bucket (если не указан, используется дефолтный)

        Возвращает:
            True если скачивание успешно
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")

        client = await self._get_client()

        await client.download_file(target_bucket, key, str(file_path))

        logger.info("s3.file_downloaded", bucket=target_bucket, key=key, path=str(file_path))
        return True

    async def download_bytes(
        self,
        key: str,
        bucket: str | None = None,
    ) -> bytes:
        """
        Скачивает данные из S3 в память.

        Аргументы:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Возвращает:
            Данные файла
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")

        client = await self._get_client()

        response = await client.get_object(Bucket=target_bucket, Key=key)
        data = await response["Body"].read()

        logger.info("s3.data_downloaded", bucket=target_bucket, key=key, bytes=len(data))
        return data

    async def open_object_body(
        self,
        key: str,
        bucket: str | None = None,
        byte_range: str | None = None,
    ) -> aioboto3.S3ObjectBody:
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")

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

        Аргументы:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Возвращает:
            True если удаление успешно
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")

        client = await self._get_client()

        await client.delete_object(Bucket=target_bucket, Key=key)

        logger.info("s3.file_deleted", bucket=target_bucket, key=key)
        return True

    async def file_exists(
        self,
        key: str,
        bucket: str | None = None,
    ) -> bool:
        """
        Проверяет существование файла в S3.

        Аргументы:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Возвращает:
            True если файл существует
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")

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

        Аргументы:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Возвращает:
            Метаданные объекта
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")

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

        Аргументы:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)
            expiration: Время жизни URL в секундах

        Возвращает:
            Временный URL
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")

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

        Аргументы:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)

        Возвращает:
            Публичный URL
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")

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

        Аргументы:
            prefix: Префикс для фильтрации объектов
            max_keys: Максимальное количество объектов
            bucket: Имя bucket (если не указан, используется дефолтный)
            start_after: S3 StartAfter — только ключи лексикографически после этого (инкрементальный обход)

        Возвращает:
            Список объектов с ключами и метаданными
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")

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

        Аргументы:
            source_key: Ключ исходного объекта
            dest_key: Ключ целевого объекта
            source_bucket: Имя исходного bucket (если не указан, используется дефолтный)
            dest_bucket: Имя целевого bucket (если не указан, используется дефолтный)

        Возвращает:
            True если копирование успешно
        """
        target_source_bucket = self.bucket_name if source_bucket is None else source_bucket
        target_dest_bucket = self.bucket_name if dest_bucket is None else dest_bucket
        if target_source_bucket == "" or target_dest_bucket == "":
            raise ValueError("Bucket is not specified")

        client = await self._get_client()

        copy_source: aioboto3.S3CopySource = {"Bucket": target_source_bucket, "Key": source_key}
        await client.copy_object(
            CopySource=copy_source,
            Bucket=target_dest_bucket,
            Key=dest_key,
        )

        logger.info(
            "s3.object_copied",
            source_bucket=target_source_bucket,
            source_key=source_key,
            dest_bucket=target_dest_bucket,
            dest_key=dest_key,
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

        Аргументы:
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)
            expiration: Время жизни URL в секундах
            method: HTTP метод ('get_object', 'put_object')

        Возвращает:
            Временный URL
        """
        target_bucket = self.bucket_name if bucket is None else bucket
        if target_bucket == "":
            raise ValueError("Bucket is not specified")

        client = await self._get_client()

        params: aioboto3.S3ObjectRequest = {"Bucket": target_bucket, "Key": key}
        url = await client.generate_presigned_url(
            method,
            Params=params,
            ExpiresIn=expiration,
        )

        return url

class S3ClientFactory:
    """Клиент платформенного хранилища. Хранилища компаний собирает object_store."""

    @staticmethod
    def create_platform_client() -> S3Client:
        settings = get_settings()
        s3 = settings.s3
        if not s3.enabled:
            raise ValueError("S3 is disabled in configuration")
        if not s3.bucket_name:
            raise ValueError("s3.bucket_name is not configured")
        if not s3.access_key_id:
            raise ValueError("s3.access_key_id is not configured")
        if not s3.secret_access_key:
            raise ValueError("s3.secret_access_key is not configured")
        ensure_sigv4_clock_aligned_with_endpoint(s3.endpoint_url)
        return S3Client(
            bucket_name=s3.bucket_name,
            access_key_id=s3.access_key_id,
            secret_access_key=s3.secret_access_key,
            region_name=s3.region_name,
            endpoint_url=s3.endpoint_url,
            provider_name=s3.provider,
            bucket_config_key=PLATFORM_STORAGE_ID,
        )

    @staticmethod
    def create_client_for_bucket(bucket_name: str) -> S3Client:
        settings = get_settings()
        if bucket_name not in (PLATFORM_STORAGE_ID, settings.s3.bucket_name):
            raise ValueError(f"Bucket {bucket_name} is not the platform storage")
        return S3ClientFactory.create_platform_client()

    @staticmethod
    def create_default_client() -> S3Client:
        return S3ClientFactory.create_platform_client()
