"""
Инструменты для генерации изображений через Nano Banana (Gemini API).
"""

import logging
from typing import Optional
from apps.agents.services.tool_decorator import tool

from core.files.processors import get_default_file_processor
from core.clients.nano_banana import NanoBananaClientFactory
from apps.agents.container import get_agents_container

logger = logging.getLogger(__name__)


@tool(
    group="Изображения",
    cost=5.0,  # 5 рублей за генерацию изображения
    billing_name="nano_banana_generation",
    free_for_plans=["premium", "enterprise"],
    is_public=True
)
async def generate_images(
    prompt: str,
    reference_file_ids: Optional[list[str]] = None,
    num_images: int = 1,
    is_editing: bool = False,
) -> str:
    """
    Генерирует изображения на основе текстового описания.
    
    Args:
        prompt: Описание того, что нужно сгенерировать
        reference_file_ids: Список ID файлов-референсов
        num_images: Количество изображений (1-4)
        is_editing: Если True, первое изображение используется как база для редактирования
        
    Returns:
        Список сгенерированных изображений в формате [FILE]...[/FILE]
    """
    try:
        container = get_agents_container()
        client = NanoBananaClientFactory.create_client(container.storage)
        if not client:
            return "❌ Nano Banana не настроен"
            
        num_images = max(1, min(num_images, 4))
        
        logger.info(f"🎨 Генерируем {num_images} изображений: {prompt[:50]}...")
        if reference_file_ids:
            logger.info(f"📎 Передаем {len(reference_file_ids)} референсных файлов в nano_banana:")
            for i, file_id in enumerate(reference_file_ids):
                logger.info(f"  [{i}] {file_id}")
        
        generated_file_ids = await client.generate_images(
            prompt=prompt,
            reference_file_ids=reference_file_ids,
            num_images=num_images,
            is_editing=is_editing,
        )
        
        if not generated_file_ids:
            return "❌ Не удалось сгенерировать изображения"
        
        file_processor = await get_default_file_processor()
        formatted_files = []
        
        for file_id in generated_file_ids:
            file_record = await file_processor.get_file_record(file_id)
            if file_record:
                formatted_file = file_processor.format_file_message(file_record)
                formatted_files.append(formatted_file)
        
        result = "\n".join(formatted_files)
        logger.info(f"✅ Сгенерировано {len(generated_file_ids)} изображений")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации изображений: {e}")
        return f"❌ Ошибка генерации изображений: {str(e)}"


# Список инструментов для экспорта
NANO_BANANA_TOOLS = [
    generate_images,
]
