"""
Инструменты для работы с файлами.
"""

from typing import Optional
from apps.agents.services.tool_decorator import tool

from apps.agents.container import get_container
from core.files.s3_client import S3ClientFactory
from apps.agents.config import get_agents_settings
settings = get_agents_settings()


@tool(group="Файлы")
async def read_file(file_id: str, provider: Optional[str] = None) -> str:
    """
    Читает содержимое файла по его ID.

    Args:
        file_id: ID файла в системе
        provider: Провайдер S3 (если не указан, используется дефолтный)

    Returns:
        Содержимое файла
    """
    # Определяем ключ для поиска файла
    if provider:
        key = f"s3:{provider}:{file_id}"
    else:
        # Используем дефолтный провайдер из конфига
        if (
            settings.s3.default_bucket
            and settings.s3.default_bucket in settings.s3.buckets
        ):
            bucket_config = settings.s3.buckets[settings.s3.default_bucket]
            provider = bucket_config.provider
            key = f"s3:{provider}:{file_id}"
        else:
            # Fallback на первый доступный провайдер
            for bucket_name, bucket_config in settings.s3.buckets.items():
                if bucket_config.enabled:
                    key = f"s3:{bucket_config.provider}:{file_id}"
                    break
            else:
                return "❌ Нет доступных S3 провайдеров"

    file_repo = get_container().file_repository
    file_record = await file_repo.get_by_s3_key(provider, file_id)

    if not file_record:
        debug_info = f"Ключ: s3:{provider}:{file_id}, Default bucket: {settings.s3.default_bucket}"

        for bucket_name, bucket_config in settings.s3.buckets.items():
            if bucket_config.enabled:
                test_record = await file_repo.get_by_s3_key(bucket_config.provider, file_id)
                if test_record:
                    debug_info += f", НАЙДЕН: s3:{bucket_config.provider}:{file_id}"
                    file_record = test_record
                    provider = bucket_config.provider
                    break
                else:
                    debug_info += f", НЕ НАЙДЕН: s3:{bucket_config.provider}:{file_id}"

        if not file_record:
            return f"❌ Файл с ID {file_id} не найден. {debug_info}"

    file_info = file_record

    if file_info.status.value != "uploaded":
        return f"❌ Файл {file_info.original_name} недоступен (статус: {file_info.status.value})"

    s3_client = S3ClientFactory.create_default_client()

    if not s3_client:
        return "❌ S3 клиент недоступен"

    file_content = await s3_client.download_bytes(file_info.s3_key)
    await s3_client.close()

    if file_content is None:
        return f"❌ Не удалось скачать файл {file_info.original_name}"

    content_type = file_info.content_type.lower()
    file_name = file_info.original_name.lower()

    # Проверяем по MIME типу или по расширению файла
    is_text_file = (
        content_type.startswith("text/")
        or content_type in ["application/json", "application/xml"]
        or file_name.endswith(
            (
                ".txt",
                ".csv",
                ".log",
                ".md",
                ".py",
                ".js",
                ".html",
                ".css",
                ".sql",
                ".yaml",
                ".yml",
            )
        )
    )

    if is_text_file:
        try:
            text_content = file_content.decode("utf-8")
            return f"📄 Файл: {file_info['original_name']}\n\n{text_content}"
        except UnicodeDecodeError:
            # Если не удалось декодировать как UTF-8, пробуем другие кодировки
            try:
                text_content = file_content.decode("cp1251")  # Русская кодировка
                return f"📄 Файл: {file_info['original_name']}\n\n{text_content}"
            except UnicodeDecodeError:
                # Если все попытки провалились, возвращаем как бинарный
                pass

    # Для остальных типов возвращаем метаданные
    return (
        f"📁 Файл: {file_info['original_name']}\n"
        f"Тип: {file_info['content_type']}\n"
        f"Размер: {file_info['file_size']} байт\n"
        f"Содержимое: бинарный файл, чтение недоступно"
    )


# Список доступных инструментов для экспорта
FILE_TOOLS = [
    read_file,
]
