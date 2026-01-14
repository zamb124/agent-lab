#!/usr/bin/env python3
"""
Скрипт для инициализации MinIO buckets в dev окружении.
Создает необходимые buckets если их нет.

Usage:
    python scripts/init_minio.py
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def init_minio_buckets():
    """Создает необходимые buckets в MinIO"""
    try:
        import aioboto3
        from botocore.exceptions import ClientError
        
        # Список buckets для создания
        buckets_to_create = [
            'files',       # Для RAG документов
            'test-bucket', # Для тестов
        ]
        
        # Подключение к MinIO
        session = aioboto3.Session()
        async with session.client(
            's3',
            endpoint_url='http://localhost:9000',
            aws_access_key_id='minioadmin',
            aws_secret_access_key='minioadmin',
            region_name='us-east-1',
        ) as client:
            for bucket_name in buckets_to_create:
                try:
                    # Проверяем существование bucket
                    await client.head_bucket(Bucket=bucket_name)
                    print(f"✅ Bucket '{bucket_name}' уже существует")
                except ClientError as e:
                    error_code = e.response.get('Error', {}).get('Code')
                    if error_code == '404':
                        # Bucket не существует - создаем
                        await client.create_bucket(Bucket=bucket_name)
                        print(f"✅ Создан bucket '{bucket_name}'")
                    else:
                        print(f"⚠️  Ошибка при проверке bucket '{bucket_name}': {e}")
            
            print("\n✅ Инициализация MinIO завершена успешно!")
            
    except ImportError:
        print("❌ Не установлен aioboto3. Установите: pip install aioboto3")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка при инициализации MinIO: {e}")
        print("\nУбедитесь что MinIO запущен:")
        print("  docker-compose -f docker-compose-dev.yaml up -d minio")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(init_minio_buckets())

