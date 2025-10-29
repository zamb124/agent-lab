"""
Nano Banana клиент для генерации изображений через OpenRouter.
Использует LLM с multimodal support вместо прямого обращения к Google.
"""

import logging
import base64
from typing import List, Optional

from ..config import settings
from .s3_client import S3ClientFactory
from app.core.container import get_container

logger = logging.getLogger(__name__)


class NanoBananaClient:
    """
    Клиент для генерации изображений через OpenRouter.
    Использует LLM с multimodal support.
    """
    
    def __init__(
        self,
        model_name: str = "google/gemini-2.5-flash-preview-image",
        timeout: int = 60,
    ):
        self.model_name = model_name
        self.timeout = timeout
        self._storage = get_container().storage
        self._llm = None
    
    async def _get_llm(self):
        """Получает LLM с multimodal support"""
        if self._llm is None:
            from ..llm_factory import get_llm
            self._llm = get_llm(model=self.model_name)
        return self._llm
    
    async def generate_images(
        self,
        prompt: str,
        reference_file_ids: Optional[List[str]] = None,
        num_images: int = 1,
        is_editing: bool = False,
    ) -> List[str]:
        """
        Генерирует изображения через LLM с multimodal output.
        
        Args:
            prompt: Текстовое описание для генерации
            reference_file_ids: ID файлов-референсов для использования в генерации
            num_images: Количество изображений для генерации
            is_editing: Если True, первое изображение используется как база для редактирования
            
        Returns:
            Список file_id сгенерированных изображений
        """
        logger.info(f"🎨 Генерация {num_images} изображений через LLM: {prompt[:50]}...")
        
        # Формируем multimodal content
        content = []
        
        # Если режим редактирования - добавляем жесткие инструкции в начало
        if is_editing and reference_file_ids:
            content.append({
                "type": "text",
                "text": """🚨 CRITICAL: PHOTO EDITING TASK - ABSOLUTE PROHIBITION ON GENERATION 🚨

**YOU ARE FORBIDDEN FROM:**
- Generating a NEW person (different face, body, identity, gender)
- Creating a NEW background or scene
- Generating a NEW image from scratch
- Replacing the person in the BASE IMAGE
- Changing the person's appearance, face, body, or identity
- **IMPROVING or ENHANCING the person's appearance** (better skin, smoother features, perfect makeup, etc.)
- **IMPROVING or CHANGING the person's clothing** (making it more fashionable, cleaner, newer, better fitting)
- **TOUCHING UP or BEAUTIFYING** any part of the person or their clothing
- **REMOVING or FIXING imperfections** in the person's appearance or clothing

**YOU MUST:**
- EDIT the EXISTING BASE IMAGE (Image #1) ONLY
- PRESERVE the EXACT person, face, body, pose, background, and lighting
- PRESERVE the EXACT clothing as it appears (keep all wrinkles, wear, style, condition)
- PRESERVE all imperfections, natural features, and realistic appearance
- ADD the product to the EXISTING person in the BASE IMAGE
- Keep 98-99% of the BASE IMAGE unchanged
- Only modify 1-2% to add the product

**IF YOU GENERATE A NEW PERSON OR NEW IMAGE, THIS IS A CRITICAL FAILURE.**

The BASE IMAGE below shows the EXACT person you must preserve. Do NOT create a new person."""
            })
        
        # Добавляем референсные изображения если есть
        if reference_file_ids:
            logger.info(f"📎 Добавляем {len(reference_file_ids)} референсных изображений")
            from ..file_processor import get_default_file_processor
            file_processor = await get_default_file_processor()
            
            for idx, file_id in enumerate(reference_file_ids):
                record = await file_processor.get_file_record(file_id)
                if record:
                    # Загружаем файл из S3
                    s3_client = S3ClientFactory.create_client_for_bucket(record.s3_bucket)
                    file_bytes = await s3_client.download_bytes(record.s3_key)
                    await s3_client.close()
                    
                    if file_bytes:
                        # Конвертируем в base64
                        base64_data = base64.b64encode(file_bytes).decode('utf-8')
                        
                        # Если это режим редактирования и первое изображение - добавляем с явной меткой
                        if is_editing and idx == 0:
                            # Сначала добавляем текст с инструкцией о базовом изображении
                            content.append({
                                "type": "text",
                                "text": """BASE IMAGE TO EDIT (Image #1) - DO NOT GENERATE NEW IMAGE

**THIS IS THE EXISTING PHOTOGRAPH - YOU MUST EDIT IT, NOT REPLACE IT:**

CRITICAL RULES FOR BASE IMAGE:
1. The person in this image MUST remain IDENTICAL (same face, same body, same identity, same gender, same clothing, same hair, same pose)
2. The background in this image MUST remain IDENTICAL
3. The lighting in this image MUST remain IDENTICAL  
4. The person's clothing MUST remain EXACTLY as shown (same style, condition, wrinkles, wear, fit)
5. DO NOT improve, enhance, or beautify the person's appearance (skin, features, makeup, etc.)
6. DO NOT improve, update, or change the person's clothing (fashion, condition, fit, cleanliness)
7. DO NOT touch up, remove imperfections, or "fix" anything about the person or their clothing
8. You are ONLY allowed to ADD the product to this person - nothing else changes
9. DO NOT generate a new person or new image
10. DO NOT replace the person's face, body, or identity
11. DO NOT change the background or scene

**IF THE OUTPUT SHOWS A DIFFERENT PERSON OR DIFFERENT BACKGROUND, YOU HAVE FAILED.**

After this base image, you will see reference images of the product. Your task is to add ONLY the product to this EXACT person in this EXACT image."""
                            })
                        
                        # Добавляем изображение
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{record.content_type};base64,{base64_data}"
                            }
                        })
                        
                        # Если это режим редактирования и не первое изображение - добавляем метку референса
                        if is_editing and idx > 0:
                            content.append({
                                "type": "text",
                                "text": f"""REFERENCE IMAGE #{idx + 1} - PRODUCT TO COPY

**CRITICAL:** This is a REFERENCE of the product. You must:
1. Extract ONLY the product from this reference image
2. Copy it EXACTLY (color, pattern, shape, details, size)
3. Add it to the BASE IMAGE (Image #1) - the EXISTING person
4. DO NOT create a new person or use the person from this reference
5. DO NOT generate anything new - only copy the product to the base image

Remember: Edit the BASE IMAGE, do NOT generate a new image."""
                            })
                        
                        logger.info(f"📎 Добавлено изображение {file_id} (индекс {idx})")
                    else:
                        logger.warning(f"⚠️ Не удалось загрузить файл {file_id}")
                else:
                    logger.warning(f"⚠️ Файл {file_id} не найден")
        
        # Добавляем основной prompt в конец, чтобы он конкретизировал задачу
        content.append({"type": "text", "text": prompt})
        
        # Получаем LLM
        llm = await self._get_llm()
        
        # Вызываем LLM (ChatOpenAIWithBilling автоматически обработает images в ответе)
        response = await llm.ainvoke([{
            "role": "user",
            "content": content
        }])
        
        # Парсим file_ids из ответа используя FileProcessor
        from ..file_processor import FileProcessor
        file_info_list = FileProcessor.extract_file_info_from_message(response.content)
        file_ids = [info["file_id"] for info in file_info_list if info.get("file_id")]
        
        if file_ids:
            logger.info(f"✅ Сгенерировано {len(file_ids)} изображений: {file_ids}")
        else:
            logger.warning(f"⚠️ Не удалось найти file_id в ответе LLM")
            logger.info(f"Response content: {response.content[:500]}")
        
        return file_ids


class NanoBananaClientFactory:
    """Фабрика для создания Nano Banana клиентов"""
    
    @staticmethod
    def create_client() -> NanoBananaClient:
        """Создает клиент на основе конфигурации"""
        if not hasattr(settings, 'nano_banana') or not settings.nano_banana.enabled:
            raise ValueError("Nano Banana не настроен в конфигурации")
        
        return NanoBananaClient(
            model_name=settings.nano_banana.model_name,
            timeout=settings.nano_banana.timeout,
        )


# Глобальный экземпляр
_default_nano_banana_client: Optional[NanoBananaClient] = None


async def get_default_nano_banana_client() -> Optional[NanoBananaClient]:
    """Получает дефолтный Nano Banana клиент"""
    global _default_nano_banana_client
    
    if _default_nano_banana_client is None:
        try:
            if hasattr(settings, 'nano_banana') and settings.nano_banana.enabled:
                _default_nano_banana_client = NanoBananaClientFactory.create_client()
                logger.info("✅ Инициализирован дефолтный Nano Banana клиент (через OpenRouter)")
            else:
                logger.info("ℹ️ Nano Banana не настроен в конфигурации")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Nano Banana клиента: {e}")
            return None
    
    return _default_nano_banana_client


async def close_default_nano_banana_client():
    """Закрывает дефолтный Nano Banana клиент"""
    global _default_nano_banana_client
    
    if _default_nano_banana_client:
        _default_nano_banana_client = None
        logger.info("✅ Дефолтный Nano Banana клиент закрыт")
