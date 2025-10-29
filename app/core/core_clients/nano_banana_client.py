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
    ) -> List[str]:
        """
        Генерирует изображения через LLM с multimodal output.
        
        Args:
            prompt: Текстовое описание для генерации
            reference_file_ids: ID файлов-референсов для использования в генерации
            num_images: Количество изображений для генерации
            
        Returns:
            Список file_id сгенерированных изображений
        """
        logger.info(f"🎨 Генерация {num_images} изображений через LLM: {prompt[:50]}...")
        
        # Формируем multimodal content
        content = [{"type": "text", "text": prompt}]
        
        # Добавляем референсные изображения если есть
        if reference_file_ids:
            logger.info(f"📎 Добавляем {len(reference_file_ids)} референсных изображений")
            from ..file_processor import get_default_file_processor
            file_processor = await get_default_file_processor()
            
            for file_id in reference_file_ids:
                record = await file_processor.get_file_record(file_id)
                if record:
                    # Загружаем файл из S3
                    s3_client = S3ClientFactory.create_client_for_bucket(record.s3_bucket)
                    file_bytes = await s3_client.download_bytes(record.s3_key)
                    await s3_client.close()
                    
                    if file_bytes:
                        # Конвертируем в base64
                        base64_data = base64.b64encode(file_bytes).decode('utf-8')
                        
                        # Добавляем в content
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{record.content_type};base64,{base64_data}"
                            }
                        })
                        logger.info(f"📎 Добавлено изображение {file_id}")
                    else:
                        logger.warning(f"⚠️ Не удалось загрузить файл {file_id}")
                else:
                    logger.warning(f"⚠️ Файл {file_id} не найден")
        
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
