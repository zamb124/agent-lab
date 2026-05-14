"""
FilesResource - wrapper для files ресурса.

Предоставляет доступ к S3/MinIO файлам.
"""

from typing import Any, Dict, List, Optional

from core.logging import get_logger

logger = get_logger(__name__)


class FilesResource:
    """
    Ресурс для работы с файлами в S3/MinIO.

    Пример:
        content = await templates.read("email.txt")

        files = await storage.list()

        await storage.write("report.txt", "Report content")
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        endpoint_url: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        region: str = "us-east-1",
        container: Any = None,
    ):
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.endpoint_url = endpoint_url
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region
        self._container = container
        self._s3_client = None

    def _get_full_path(self, path: str) -> str:
        """Возвращает полный путь с префиксом."""
        if self.prefix:
            return f"{self.prefix}/{path}"
        return path

    async def _get_s3_client(self):
        """Получить или создать S3 клиент."""
        if self._s3_client is not None:
            return self._s3_client

        from core.files import S3Client

        # Если есть явные credentials - используем их
        if self.access_key_id and self.secret_access_key:
            self._s3_client = S3Client(
                bucket_name=self.bucket,
                access_key_id=self.access_key_id,
                secret_access_key=self.secret_access_key,
                region_name=self.region,
                endpoint_url=self.endpoint_url,
                provider_name="minio" if self.endpoint_url else "aws",
            )
            return self._s3_client

        # Иначе пробуем дефолтный клиент из settings
        from core.files import get_default_s3_client
        client = await get_default_s3_client()
        if client is None:
            raise RuntimeError(
                "S3 клиент не настроен. Укажите access_key_id и secret_access_key "
                "в конфиге ресурса или настройте settings.s3"
            )
        self._s3_client = client
        return self._s3_client

    async def read(self, path: str, encoding: str = "utf-8") -> str:
        """
        Прочитать файл как текст.

        Args:
            path: Путь к файлу (относительно prefix)
            encoding: Кодировка

        Returns:
            Содержимое файла
        """
        content = await self.read_bytes(path)
        return content.decode(encoding)

    async def read_bytes(self, path: str) -> bytes:
        """
        Прочитать файл как bytes.

        Args:
            path: Путь к файлу

        Returns:
            Бинарное содержимое
        """
        s3 = await self._get_s3_client()
        full_path = self._get_full_path(path)

        return await s3.download_bytes(full_path)

    async def write(self, path: str, content: str, encoding: str = "utf-8") -> str:
        """
        Записать файл.

        Args:
            path: Путь к файлу
            content: Содержимое
            encoding: Кодировка

        Returns:
            Путь к сохранённому файлу
        """
        return await self.write_bytes(path, content.encode(encoding))

    async def write_bytes(self, path: str, content: bytes) -> str:
        """
        Записать бинарный файл.

        Args:
            path: Путь к файлу
            content: Бинарное содержимое

        Returns:
            Путь к сохранённому файлу
        """
        s3 = await self._get_s3_client()
        full_path = self._get_full_path(path)

        await s3.upload_bytes(content, full_path)
        return full_path

    async def list(self, path: str = "") -> List[Dict[str, Any]]:
        """
        Список файлов в директории.

        Args:
            path: Путь к директории

        Returns:
            Список файлов с метаданными
        """
        s3 = await self._get_s3_client()
        full_path = self._get_full_path(path)

        return await s3.list_objects(prefix=full_path)

    async def exists(self, path: str) -> bool:
        """
        Проверить существование файла.

        Args:
            path: Путь к файлу

        Returns:
            True если файл существует
        """
        from botocore.exceptions import ClientError

        s3 = await self._get_s3_client()
        full_path = self._get_full_path(path)

        try:
            return await s3.file_exists(full_path)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            raise

    async def delete(self, path: str) -> bool:
        """
        Удалить файл.

        Args:
            path: Путь к файлу

        Returns:
            True если удалён
        """
        s3 = await self._get_s3_client()
        full_path = self._get_full_path(path)

        return await s3.delete_file(full_path)

    def __repr__(self) -> str:
        return f"<FilesResource bucket={self.bucket} prefix={self.prefix}>"
