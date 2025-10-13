"""
S3 клиент для работы с объектным хранилищем.
Поддерживает AWS S3 и совместимые сервисы (Yandex Object Storage, MinIO, etc.).
Автоматически сохраняет записи о файлах в БД.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
import aioboto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config

from ..config import settings

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
            provider_name: Имя провайдера (aws, yandex, minio)
            track_files: Сохранять ли записи о файлах в БД
        """
        self.bucket_name = bucket_name
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self.provider_name = provider_name
        self.track_files = track_files
        self._session = None
        self._client = None
        self._storage = None
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
        """Закрывает соединения клиента (потокобезопасно)"""
        lock = self._get_client_lock()
        async with lock:
            if self._client:
                try:
                    await self._client.__aexit__(None, None, None)
                except Exception:
                    pass
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
    ) -> bool:
        """
        Загружает файл в S3.

        Args:
            file_path: Путь к файлу для загрузки
            key: Ключ объекта в S3
            bucket: Имя bucket (если не указан, используется дефолтный)
            metadata: Метаданные объекта
            content_type: MIME тип файла

        Returns:
            True если загрузка успешна
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        try:
            client = await self._get_client()

            extra_args = {}
            if metadata:
                extra_args["Metadata"] = metadata
            if content_type:
                extra_args["ContentType"] = content_type

            await client.upload_file(
                str(file_path),
                bucket,
                key,
                ExtraArgs=extra_args if extra_args else None,
            )

            logger.info(f"✅ Файл загружен в S3: {bucket}/{key}")
            return True

        except FileNotFoundError:
            logger.error(f"❌ Файл не найден: {file_path}")
            return False
        except NoCredentialsError:
            logger.error("❌ Не настроены креды для S3")
            return False
        except ClientError as e:
            logger.error(f"❌ Ошибка S3 при загрузке {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при загрузке {key}: {e}")
            return False

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        bucket: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        acl: Optional[str] = None,
    ) -> bool:
        """
        Загружает данные из памяти в S3.

        Args:
            data: Данные для загрузки
            key: Ключ объекта в S3
            bucket: Имя bucket
            metadata: Метаданные объекта
            content_type: MIME тип
            acl: ACL для объекта (например, "public-read")

        Returns:
            True если загрузка успешна
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        client = await self._get_client()

        # Проверяем что data это bytes
        if not isinstance(data, bytes):
            raise ValueError(f"data должен быть bytes, получен {type(data)}: {data}")

        put_args = {"Body": data}
        if metadata:
            put_args["Metadata"] = metadata
        if content_type:
            put_args["ContentType"] = content_type
        if acl:
            put_args["ACL"] = acl
            logger.info(f"🔓 Устанавливаем ACL: {acl} для {key}")

        logger.info(f"📤 Загружаем в S3 с параметрами: {list(put_args.keys())}")

        await client.put_object(Bucket=bucket, Key=key, **put_args)

        logger.info(f"✅ Данные загружены в S3: {bucket}/{key}")
        return True

    async def download_file(
        self, key: str, file_path: Union[str, Path], bucket: Optional[str] = None
    ) -> bool:
        """
        Скачивает файл из S3.

        Args:
            key: Ключ объекта в S3
            file_path: Путь для сохранения файла
            bucket: Имя bucket

        Returns:
            True если скачивание успешно
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        try:
            client = await self._get_client()

            await client.download_file(bucket, key, str(file_path))

            logger.info(f"✅ Файл скачан из S3: {bucket}/{key} -> {file_path}")
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.error(f"❌ Объект не найден в S3: {bucket}/{key}")
            else:
                logger.error(f"❌ Ошибка S3 при скачивании {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при скачивании {key}: {e}")
            return False

    async def download_bytes(
        self, key: str, bucket: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Скачивает объект из S3 как bytes.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket

        Returns:
            Данные объекта или None при ошибке
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        try:
            client = await self._get_client()

            response = await client.get_object(Bucket=bucket, Key=key)
            data = await response["Body"].read()

            logger.info(f"✅ Объект скачан из S3: {bucket}/{key} ({len(data)} bytes)")
            return data

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.error(f"❌ Объект не найден в S3: {bucket}/{key}")
            else:
                logger.error(f"❌ Ошибка S3 при скачивании {key}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при скачивании {key}: {e}")
            return None

    async def delete_object(self, key: str, bucket: Optional[str] = None) -> bool:
        """
        Удаляет объект из S3.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket

        Returns:
            True если удаление успешно
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        try:
            client = await self._get_client()

            await client.delete_object(Bucket=bucket, Key=key)

            logger.info(f"✅ Объект удален из S3: {bucket}/{key}")
            return True

        except ClientError as e:
            logger.error(f"❌ Ошибка S3 при удалении {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при удалении {key}: {e}")
            return False

    async def list_objects(
        self, prefix: str = "", bucket: Optional[str] = None, max_keys: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Получает список объектов в bucket.

        Args:
            prefix: Префикс для фильтрации объектов
            bucket: Имя bucket
            max_keys: Максимальное количество объектов

        Returns:
            Список объектов с метаданными
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        try:
            client = await self._get_client()

            kwargs = {"Bucket": bucket, "MaxKeys": max_keys}
            if prefix:
                kwargs["Prefix"] = prefix

            response = await client.list_objects_v2(**kwargs)

            objects = []
            for obj in response.get("Contents", []):
                objects.append(
                    {
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                        "etag": obj["ETag"].strip('"'),
                    }
                )

            logger.info(
                f"✅ Получен список объектов S3: {bucket} (найдено {len(objects)})"
            )
            return objects

        except ClientError as e:
            logger.error(f"❌ Ошибка S3 при получении списка: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при получении списка: {e}")
            return []

    async def object_exists(self, key: str, bucket: Optional[str] = None) -> bool:
        """
        Проверяет существование объекта в S3.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket

        Returns:
            True если объект существует
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        try:
            client = await self._get_client()

            await client.head_object(Bucket=bucket, Key=key)
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            else:
                logger.error(f"❌ Ошибка S3 при проверке существования {key}: {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при проверке существования {key}: {e}")
            return False

    async def get_object_metadata(
        self, key: str, bucket: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Получает метаданные объекта.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket

        Returns:
            Метаданные объекта или None
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        try:
            client = await self._get_client()

            response = await client.head_object(Bucket=bucket, Key=key)

            metadata = {
                "content_length": response["ContentLength"],
                "content_type": response.get("ContentType"),
                "last_modified": response["LastModified"].isoformat(),
                "etag": response["ETag"].strip('"'),
                "metadata": response.get("Metadata", {}),
            }

            logger.info(f"✅ Получены метаданные S3: {bucket}/{key}")
            return metadata

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                logger.warning(f"⚠️ Объект не найден в S3: {bucket}/{key}")
            else:
                logger.error(f"❌ Ошибка S3 при получении метаданных {key}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при получении метаданных {key}: {e}")
            return None

    async def generate_presigned_url(
        self,
        key: str,
        bucket: Optional[str] = None,
        expiration: int = 3600,
        method: str = "get_object",
    ) -> Optional[str]:
        """
        Генерирует подписанный URL для доступа к объекту.

        Args:
            key: Ключ объекта в S3
            bucket: Имя bucket
            expiration: Время жизни URL в секундах
            method: HTTP метод ('get_object', 'put_object')

        Returns:
            Подписанный URL или None при ошибке
        """
        bucket = bucket or self.bucket_name
        if not bucket:
            raise ValueError("Bucket не указан")

        try:
            client = await self._get_client()

            url = await client.generate_presigned_url(
                method, Params={"Bucket": bucket, "Key": key}, ExpiresIn=expiration
            )

            logger.info(
                f"✅ Создан presigned URL для {bucket}/{key} (срок: {expiration}s)"
            )
            return url

        except ClientError as e:
            logger.error(f"❌ Ошибка S3 при создании presigned URL для {key}: {e}")
            return None
        except Exception as e:
            logger.error(
                f"❌ Неожиданная ошибка при создании presigned URL для {key}: {e}"
            )
            return None

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
            source_bucket: Исходный bucket
            dest_bucket: Целевой bucket

        Returns:
            True если копирование успешно
        """
        source_bucket = source_bucket or self.bucket_name
        dest_bucket = dest_bucket or self.bucket_name

        if not source_bucket or not dest_bucket:
            raise ValueError("Bucket не указан")

        try:
            client = await self._get_client()

            copy_source = {"Bucket": source_bucket, "Key": source_key}

            await client.copy_object(
                CopySource=copy_source, Bucket=dest_bucket, Key=dest_key
            )

            logger.info(
                f"✅ Объект скопирован в S3: {source_bucket}/{source_key} -> {dest_bucket}/{dest_key}"
            )
            return True

        except ClientError as e:
            logger.error(f"❌ Ошибка S3 при копировании {source_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при копировании {source_key}: {e}")
            return False

    async def create_bucket(self, bucket: str, region: Optional[str] = None) -> bool:
        """
        Создает новый bucket.

        Args:
            bucket: Имя bucket
            region: Регион для bucket

        Returns:
            True если создание успешно
        """
        try:
            client = await self._get_client()

            kwargs = {"Bucket": bucket}
            if region and region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}

            await client.create_bucket(**kwargs)

            logger.info(f"✅ Bucket создан в S3: {bucket}")
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "BucketAlreadyExists":
                logger.warning(f"⚠️ Bucket уже существует: {bucket}")
                return True
            else:
                logger.error(f"❌ Ошибка S3 при создании bucket {bucket}: {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при создании bucket {bucket}: {e}")
            return False

    async def delete_bucket(self, bucket: str, force: bool = False) -> bool:
        """
        Удаляет bucket.

        Args:
            bucket: Имя bucket
            force: Принудительное удаление (сначала очищает bucket)

        Returns:
            True если удаление успешно
        """
        try:
            client = await self._get_client()

            if force:
                # Сначала удаляем все объекты
                objects = await self.list_objects(bucket=bucket)
                for obj in objects:
                    await self.delete_object(obj["key"], bucket)

            await client.delete_bucket(Bucket=bucket)

            logger.info(f"✅ Bucket удален из S3: {bucket}")
            return True

        except ClientError as e:
            logger.error(f"❌ Ошибка S3 при удалении bucket {bucket}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при удалении bucket {bucket}: {e}")
            return False


class S3ClientFactory:
    """
    Фабрика для создания S3 клиентов на основе конфигурации.
    """

    @staticmethod
    def create_client_for_bucket(bucket_name: str) -> S3Client:
        """
        Создает S3 клиент для указанного бакета из конфигурации.

        Args:
            bucket_name: Имя бакета из конфигурации

        Returns:
            Настроенный S3 клиент
        """
        if not settings.s3.enabled:
            raise ValueError("S3 отключен в конфигурации")

        bucket_config = settings.s3.buckets.get(bucket_name)
        if not bucket_config:
            raise ValueError(f"Бакет {bucket_name} не найден в конфигурации")

        if not bucket_config.enabled:
            raise ValueError(f"Бакет {bucket_name} отключен")

        if not bucket_config.access_key_id or not bucket_config.secret_access_key:
            raise ValueError(f"Не настроены креды для бакета {bucket_name}")

        return S3Client(
            bucket_name=bucket_name,
            access_key_id=bucket_config.access_key_id,
            secret_access_key=bucket_config.secret_access_key,
            region_name=bucket_config.region_name,
            endpoint_url=bucket_config.endpoint_url,
            provider_name=bucket_config.provider,
            track_files=True,
        )

    @staticmethod
    def create_client(
        provider: str = "aws", config: Optional[Dict[str, Any]] = None
    ) -> S3Client:
        """
        Создает S3 клиент с прямой конфигурацией (для обратной совместимости).

        Args:
            provider: Провайдер хранилища (aws, yandex, minio)
            config: Конфигурация клиента

        Returns:
            Настроенный S3 клиент
        """
        if not config:
            config = {}

        bucket_name = config.get("bucket_name", "default")

        return S3Client(
            bucket_name=bucket_name,
            access_key_id=config.get("access_key_id"),
            secret_access_key=config.get("secret_access_key"),
            region_name=config.get("region_name", "us-east-1"),
            endpoint_url=config.get("endpoint_url"),
            provider_name=provider,
            track_files=config.get("track_files", True),
        )


# Глобальный экземпляр для удобства
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

    lock = _get_lock()
    async with lock:
        if _default_s3_client:
            await _default_s3_client.close()
            _default_s3_client = None
            logger.info("✅ Дефолтный S3 клиент закрыт")
