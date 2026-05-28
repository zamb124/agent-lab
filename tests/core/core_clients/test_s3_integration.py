"""
Интеграционные тесты S3 клиента.
Работают с реальным S3 хранилищем и БД.
"""
import os
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest

from core.files.models import FileRecord, FileStatus
from core.files.s3_client import S3ClientFactory


def get_test_bucket_name():
    """Получить имя тестового bucket в зависимости от окружения"""
    if os.getenv("TESTING") == "true":
        return "test-bucket"
    return "test-bucket"


def skip_if_s3_disabled():
    """Проверка доступности S3"""
    bucket_name = get_test_bucket_name()
    try:
        S3ClientFactory.create_client_for_bucket(bucket_name)
    except ValueError:
        raise


def skip_if_s3_fails(test_func):
    """Декоратор для пропуска тестов при проблемах с S3"""
    async def wrapper(*args, **kwargs):
        try:
            return await test_func(*args, **kwargs)
        except Exception:

            raise
    return wrapper


@pytest.fixture
async def minio_bucket():
    """Создает bucket в MinIO если его нет"""
    bucket_name = get_test_bucket_name()
    try:
        client = S3ClientFactory.create_client_for_bucket(bucket_name)

        s3_client = await client._get_client()
        physical = client.bucket_name
        try:
            await s3_client.head_bucket(Bucket=physical)
        except Exception:
            await s3_client.create_bucket(Bucket=physical)

        yield client

        await client.close()
    except Exception:
        raise


@pytest.mark.asyncio
class TestS3Integration:
    """Интеграционные тесты S3 с реальным хранилищем"""

    async def test_s3_client_creation_from_config(self):
        """Тест создания S3 клиента из конфигурации"""
        skip_if_s3_disabled()
        from core.config import get_settings

        bucket_name = get_test_bucket_name()
        client = S3ClientFactory.create_client_for_bucket(bucket_name)
        bucket_config = get_settings().s3.buckets[bucket_name]
        expected_physical = bucket_config.bucket_name or bucket_name

        assert client.bucket_name == expected_physical
        assert client.require_bucket_config_key() == bucket_name
        assert client.provider_name == bucket_config.provider
        assert client.endpoint_url == bucket_config.endpoint_url
        assert client.access_key_id == bucket_config.access_key_id
        assert client.track_files

        await client.close()

    async def test_s3_client_creation_invalid_bucket(self):
        """Тест создания клиента для несуществующего бакета"""
        skip_if_s3_disabled()
        with pytest.raises(ValueError, match="не найден в конфигурации"):
            S3ClientFactory.create_client_for_bucket('nonexistent-bucket')

    async def test_bucket_config_key_on_factory_client(self):
        """FileRecord.s3_bucket = ключ конфига; клиент знает физическое имя и ключ."""
        skip_if_s3_disabled()
        from core.config import get_settings

        s = get_settings()
        for cfg_key, bucket_cfg in s.s3.buckets.items():
            if not bucket_cfg.enabled:
                continue
            c = S3ClientFactory.create_client_for_bucket(cfg_key)
            try:
                assert c.require_bucket_config_key() == cfg_key
            finally:
                await c.close()

    async def test_upload_and_download_bytes(self, minio_bucket):
        """Тест загрузки и скачивания данных в MinIO S3"""
        client = minio_bucket

        # Создаем тестовые данные
        test_data = b"Test file content for S3 integration test"
        # Используем более простой путь для Yandex Object Storage
        test_key = f"pytest-{uuid.uuid4().hex[:8]}.txt"

        try:
            # Загружаем данные
            upload_success = await client.upload_bytes(
                data=test_data,
                key=test_key,
                content_type="text/plain",
                metadata={"test": "integration", "source": "pytest"}
            )

            assert upload_success, "S3 upload_bytes вернул False (права доступа или конфиг бакета)"

            print(f"✅ Файл загружен в S3: {test_key}")

            # Проверяем существование
            exists = await client.file_exists(test_key)
            assert exists
            print("✅ Файл существует в S3")

            # Скачиваем данные
            downloaded_data = await client.download_bytes(test_key)
            assert downloaded_data == test_data
            print(f"✅ Файл скачан из S3: {len(downloaded_data)} bytes")

            # Получаем метаданные
            metadata = await client.get_object_metadata(test_key)
            assert metadata.content_length == len(test_data)
            print(f"✅ Метаданные получены: {metadata.content_length} bytes")

        finally:
            # Очищаем тестовый файл
            try:
                delete_success = await client.delete_file(test_key)
                if delete_success:
                    print("✅ Тестовый файл удален")
            except Exception:
                pass

            await client.close()

    async def test_upload_file_from_disk(self, minio_bucket):
        """Тест загрузки файла с диска в MinIO S3"""
        client = minio_bucket

        # Создаем временный файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test file content from disk")
            temp_path = Path(f.name)

        test_key = f"pytest-disk-{uuid.uuid4().hex[:8]}.txt"
        download_path = temp_path.with_suffix('.downloaded.txt')

        try:
            # Загружаем файл
            upload_success = await client.upload_file(
                file_path=temp_path,
                key=test_key,
                content_type="text/plain"
            )

            assert upload_success, "S3 upload_file вернул False (права доступа или конфиг бакета)"
            print(f"✅ Файл загружен с диска в S3: {test_key}")

            # Проверяем что файл существует
            exists = await client.file_exists(test_key)
            assert exists

            # Скачиваем обратно на диск
            download_success = await client.download_file(test_key, download_path)
            assert download_success

            # Проверяем содержимое
            with open(download_path, 'r') as f:
                content = f.read()
            assert content == "Test file content from disk"
            print("✅ Файл скачан на диск и содержимое совпадает")

        finally:
            # Очистка
            await client.delete_file(test_key)
            temp_path.unlink(missing_ok=True)
            download_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_list_objects(self, minio_bucket):
        """Тест получения списка объектов"""
        client = minio_bucket

        # Создаем несколько тестовых файлов
        test_prefix = f"test/list_{uuid.uuid4().hex[:8]}"
        test_files = []

        try:
            for i in range(3):
                key = f"{test_prefix}/file_{i}.txt"
                data = f"Test file {i} content".encode()

                success = await client.upload_bytes(data, key, content_type="text/plain")
                assert success, "S3 upload_bytes вернул False при подготовке list_objects"
                test_files.append(key)

            print(f"✅ Создано {len(test_files)} тестовых файлов")

            objects = await client.list_objects(prefix=test_prefix, max_keys=10)
            assert len(objects) >= 3, (
                f"S3 list_objects по префиксу {test_prefix!r} вернул {len(objects)} объектов (ожидалось >= 3)"
            )
            print(f"✅ Получен список объектов: {len(objects)} файлов")

            # Проверяем что наши файлы в списке
            found_keys = [obj.key for obj in objects]
            for test_key in test_files:
                assert test_key in found_keys

        finally:
            # Очищаем тестовые файлы
            for key in test_files:
                await client.delete_file(key)
            await client.close()

    async def test_copy_object(self, minio_bucket):
        """Тест копирования объектов"""
        skip_if_s3_disabled()
        client = minio_bucket

        # Создаем исходный файл
        source_key = f"test/copy_source_{uuid.uuid4().hex[:8]}.txt"
        dest_key = f"test/copy_dest_{uuid.uuid4().hex[:8]}.txt"
        test_data = b"Content for copy test"

        try:
            # Загружаем исходный файл
            upload_success = await client.upload_bytes(test_data, source_key)
            assert upload_success, "S3 upload_bytes вернул False перед copy_object"

            # Копируем файл
            copy_success = await client.copy_object(source_key, dest_key)
            assert copy_success
            print(f"✅ Файл скопирован: {source_key} -> {dest_key}")

            # Проверяем что оба файла существуют
            source_exists = await client.file_exists(source_key)
            dest_exists = await client.file_exists(dest_key)

            assert source_exists
            assert dest_exists

            # Проверяем что содержимое одинаковое
            source_data = await client.download_bytes(source_key)
            dest_data = await client.download_bytes(dest_key)

            assert source_data == dest_data == test_data
            print("✅ Содержимое файлов одинаковое")

        finally:
            # Очистка
            await client.delete_file(source_key)
            await client.delete_file(dest_key)

    async def test_presigned_url_generation(self, minio_bucket):
        """Тест генерации подписанных URL"""
        client = minio_bucket

        test_key = f"test/presigned_{uuid.uuid4().hex[:8]}.txt"
        test_data = b"Content for presigned URL test"

        try:
            # Загружаем файл
            upload_success = await client.upload_bytes(test_data, test_key)
            assert upload_success, "S3 upload_bytes вернул False перед presigned URL"

            # Генерируем presigned URL для скачивания
            download_url = await client.generate_presigned_url(
                key=test_key,
                expiration=3600,
                method='get_object'
            )

            assert download_url is not None
            endpoint_netloc = urlparse(client.endpoint_url).netloc
            assert endpoint_netloc in download_url
            assert test_key in download_url
            print(f"✅ Presigned URL создан: {download_url[:100]}...")

            # Генерируем presigned URL для загрузки
            upload_url = await client.generate_presigned_url(
                key=f"{test_key}.upload",
                expiration=1800,
                method='put_object'
            )

            assert upload_url is not None
            print("✅ Upload presigned URL создан")

        finally:
            # Очистка
            await client.delete_file(test_key)


@pytest.mark.asyncio
class TestS3WithDatabase:
    """Тесты S3 с сохранением записей в БД"""

    async def test_file_record_creation_and_storage(self, storage, minio_bucket):
        """Тест создания и сохранения записи о файле в БД"""

        bucket_name = get_test_bucket_name()
        client = minio_bucket

        # Создаем запись о файле
        file_record = FileRecord(
            file_id=f"test_{uuid.uuid4().hex[:8]}",
            provider="minio",
            original_name="test-db-file.txt",
            s3_key="test/db-file.txt",
            s3_bucket=bucket_name,
            s3_endpoint=client.endpoint_url,
            content_type="text/plain",
            file_size=1024,
            uploaded_by="test_user",
            tags=["test", "integration"],
            metadata={"source": "pytest", "test_type": "integration"}
        )

        # Сохраняем в БД
        save_success = await storage.set(file_record.key, file_record.model_dump_json(), force_global=True)
        assert save_success
        print(f"✅ Запись о файле сохранена в БД: {file_record.key}")

        # Проверяем что запись сохранена сразу после set

        # Получаем из БД
        stored_data = await storage.get(file_record.key, force_global=True)
        assert stored_data is not None, f"Запись должна быть найдена, ключ={file_record.key}"

        # Восстанавливаем объект
        stored_record = FileRecord.model_validate_json(stored_data)

        assert stored_record.file_id == file_record.file_id
        assert stored_record.provider == file_record.provider
        assert stored_record.original_name == file_record.original_name
        assert stored_record.s3_key == file_record.s3_key
        assert stored_record.url == file_record.url
        print("✅ Запись восстановлена из БД корректно")

        # Обновляем статус
        stored_record.status = FileStatus.UPLOADED
        update_success = await storage.set(stored_record.key, stored_record.model_dump_json(), force_global=True)
        assert update_success
        print("✅ Статус файла обновлен в БД")

        # Очистка
        await storage.delete(file_record.key, force_global=True)

    async def test_full_s3_workflow_with_db(self, storage, minio_bucket):
        """Полный тест: загрузка в S3 + сохранение в БД + скачивание + удаление"""
        client = minio_bucket

        # Создаем тестовые данные
        test_data = f"Integration test content {uuid.uuid4().hex[:8]}".encode()
        file_id = f"integration_{uuid.uuid4().hex[:8]}"
        s3_key = f"test/integration/{file_id}.txt"

        # 1. Создаем запись в БД (статус UPLOADING)
        file_record = FileRecord(
            file_id=file_id,
            provider=client.provider_name,
            original_name=f"{file_id}.txt",
            s3_key=s3_key,
            s3_bucket=client.require_bucket_config_key(),
            s3_endpoint=client.endpoint_url,
            content_type="text/plain",
            file_size=len(test_data),
            uploaded_by="integration_test",
            tags=["integration", "test"],
            status=FileStatus.UPLOADING
        )

        db_save_success = await storage.set(file_record.key, file_record.model_dump_json())
        assert db_save_success
        print(f"✅ 1. Запись создана в БД: {file_record.key}")

        try:
            # 2. Загружаем файл в S3
            s3_upload_success = await client.upload_bytes(
                data=test_data,
                key=s3_key,
                content_type="text/plain",
                metadata={"file_id": file_id, "test": "integration"}
            )

            if not s3_upload_success:
                file_record.status = FileStatus.FAILED
                await storage.set(file_record.key, file_record.model_dump_json())
            assert s3_upload_success, "S3 upload_bytes вернул False в сценарии FileRecord"
            print(f"✅ 2. Файл загружен в S3: {s3_key}")

            # 3. Обновляем статус в БД
            file_record.status = FileStatus.UPLOADED
            db_update_success = await storage.set(file_record.key, file_record.model_dump_json())
            assert db_update_success
            print("✅ 3. Статус обновлен в БД: UPLOADED")

            # 4. Проверяем что файл доступен
            exists = await client.file_exists(s3_key)
            assert exists

            # 5. Скачиваем и проверяем содержимое
            downloaded_data = await client.download_bytes(s3_key)
            assert downloaded_data == test_data
            print("✅ 4. Файл скачан и содержимое совпадает")

            # 6. Проверяем метаданные S3
            s3_metadata = await client.get_object_metadata(s3_key)
            assert s3_metadata.content_length == len(test_data)
            assert s3_metadata.metadata["file_id"] == file_id
            print("✅ 5. Метаданные S3 корректны")

            # 7. Генерируем публичный URL
            public_url = file_record.url
            assert public_url is not None
            # URL может быть прямым S3 или прокси через API
            assert (client.bucket_name in public_url or "/api/v1/files/download/" in public_url)
            print(f"✅ 6. Публичный URL: {public_url}")

        finally:
            # 8. Очистка: удаляем из S3 и БД
            await client.delete_file(s3_key)
            file_record.status = FileStatus.DELETED
            await storage.set(file_record.key, file_record.model_dump_json())
            print("✅ 7. Очистка завершена")

            await client.close()


    async def test_file_record_key_format(self):
        """Тест формата ключей файлов в БД"""
        # Тестируем разные провайдеры
        providers_and_ids = [
            ("yandex", "yandex_file_123"),
            ("aws", "aws_file_456"),
            ("minio", "minio_file_789"),
            ("custom-provider", "custom_file_000")
        ]

        for provider, file_id in providers_and_ids:
            file_record = FileRecord(
                file_id=file_id,
                provider=provider,
                original_name="test.txt",
                s3_key="test/test.txt",
                s3_bucket="test-bucket",
                s3_endpoint="https://example.com",
                content_type="text/plain",
                file_size=100
            )

            expected_key = f"s3:{provider}:{file_id}"
            assert file_record.key == expected_key
            print(f"✅ Ключ для {provider}: {file_record.key}")

    async def test_default_s3_client(self):
        """Тест дефолтного S3 клиента"""
        default_client = S3ClientFactory.create_default_client()
        from core.config import get_settings

        s = get_settings()
        key = s.s3.default_bucket
        cfg = s.s3.buckets[key]
        expected_physical = cfg.bucket_name or key

        assert default_client is not None
        assert default_client.bucket_name == expected_physical
        assert default_client.require_bucket_config_key() == key
        assert default_client.provider_name == "minio"
        print(f"✅ Дефолтный клиент: {default_client.provider_name}/{default_client.bucket_name}")

        # Тестируем простую операцию
        test_key = f"test/default_{uuid.uuid4().hex[:8]}.txt"
        test_data = b"Default client test"

        try:
            upload_success = await default_client.upload_bytes(test_data, test_key)
            assert upload_success, "S3 upload_bytes вернул False для default_client"

            exists = await default_client.file_exists(test_key)
            assert exists
            print("✅ Дефолтный клиент работает корректно")

        finally:
            await default_client.delete_file(test_key)


class TestS3Configuration:
    """Тесты конфигурации S3"""

    def test_s3_config_structure(self):
        """Тест структуры S3 конфигурации"""
        from core.config import settings

        assert hasattr(settings, 's3')
        assert settings.s3.enabled
        assert settings.s3.default_bucket == "test-bucket"
        assert isinstance(settings.s3.buckets, dict)
        assert len(settings.s3.buckets) >= 1

        # Проверяем структуру бакетов
        for bucket_name, bucket_config in settings.s3.buckets.items():
            assert hasattr(bucket_config, 'provider')
            assert hasattr(bucket_config, 'access_key_id')
            assert hasattr(bucket_config, 'secret_access_key')
            assert hasattr(bucket_config, 'region_name')
            assert hasattr(bucket_config, 'endpoint_url')
            assert hasattr(bucket_config, 'enabled')
            print(f"✅ Бакет {bucket_name}: provider={bucket_config.provider}, enabled={bucket_config.enabled}")

    def test_file_record_url_generation(self):
        """Тест генерации URL для файлов через платформу"""
        # FileRecord.url всегда генерирует прокси URL через /api/v1/files/download/{file_id}
        # Это безопаснее чем прямые S3 URL

        yandex_file = FileRecord(
            file_id="yandex_test",
            provider="yandex",
            original_name="test.txt",
            s3_key="files/test.txt",
            s3_bucket="my-bucket",
            s3_endpoint="https://storage.yandexcloud.net",
            content_type="text/plain",
            file_size=100
        )

        yandex_url = yandex_file.url
        # URL должен быть прокси через нашу платформу
        assert "/api/v1/files/download/yandex_test" in yandex_url
        print(f"✅ Yandex URL (прокси): {yandex_url}")

        aws_file = FileRecord(
            file_id="aws_test",
            provider="aws",
            original_name="test.txt",
            s3_key="files/test.txt",
            s3_bucket="my-aws-bucket",
            s3_endpoint="https://s3.amazonaws.com",
            content_type="text/plain",
            file_size=100
        )

        aws_url = aws_file.url
        # URL должен быть прокси через нашу платформу
        assert "/api/v1/files/download/aws_test" in aws_url
        print(f"✅ AWS URL (прокси): {aws_url}")

        minio_file = FileRecord(
            file_id="minio_test",
            provider="minio",
            original_name="test.txt",
            s3_key="files/test.txt",
            s3_bucket="my-minio-bucket",
            s3_endpoint="http://localhost:9000",
            content_type="text/plain",
            file_size=100
        )

        minio_url = minio_file.url
        # URL должен быть прокси через нашу платформу
        assert "/api/v1/files/download/minio_test" in minio_url
        print(f"✅ MinIO URL (прокси): {minio_url}")
