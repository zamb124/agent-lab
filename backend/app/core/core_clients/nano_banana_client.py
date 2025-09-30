"""
Nano Banana клиент для генерации изображений через Gemini API.
"""

import logging
import uuid
from typing import List, Optional
import google.generativeai as genai

from ..config import settings
from ..storage import Storage
from .s3_client import S3ClientFactory

logger = logging.getLogger(__name__)


class NanoBananaClient:
    """
    Клиент для генерации изображений через Gemini API.
    """
    
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.5-flash-image-preview",
        timeout: int = 60,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout
        self._storage = Storage()
        
        genai.configure(api_key=self.api_key)
        
    async def _get_file_records(self, file_ids: List[str]) -> List[bytes]:
        """Получает данные файлов по их ID"""
        from ..file_processor import get_default_file_processor
        file_processor = await get_default_file_processor()
        file_data_list = []
        
        for file_id in file_ids:
            record = await file_processor.get_file_record(file_id)
            if record:
                # Загружаем файл из S3
                s3_client = S3ClientFactory.create_client_for_bucket(record.s3_bucket)
                file_data = await s3_client.download_bytes(record.s3_key)
                if file_data:
                    file_data_list.append(file_data)
                await s3_client.close()
            else:
                logger.warning(f"Файл {file_id} не найден")
                
        return file_data_list

    async def generate_images(
        self,
        prompt: str,
        reference_file_ids: Optional[List[str]] = None,
        num_images: int = 1,
    ) -> List[str]:
        """
        Генерирует изображения через Gemini API.
        
        Args:
            prompt: Текстовое описание для генерации
            reference_file_ids: ID файлов-референсов для использования в генерации
            num_images: Количество изображений для генерации
            
        Returns:
            Список file_id сгенерированных изображений
        """
        try:
            model = genai.GenerativeModel(self.model_name)
            
            # Подготавливаем контент для генерации
            content_parts = [prompt]
            
            # Добавляем референсные изображения если есть
            if reference_file_ids:
                logger.info(f"📎 Используем {len(reference_file_ids)} референсных файлов")
                reference_data = await self._get_file_records(reference_file_ids)
                
                for file_data in reference_data:
                    # Добавляем изображение в контент
                    content_parts.append({
                        "mime_type": "image/png",  # Предполагаем PNG, можно улучшить определение типа
                        "data": file_data
                    })
            
            logger.info(f"🎨 Генерируем {num_images} изображений с промптом: {prompt[:100]}...")
            
            generated_file_ids = []
            
            for i in range(num_images):
                response = model.generate_content(
                    content_parts,
                    generation_config=genai.GenerationConfig(
                        temperature=0.7,
                    )
                )
                
                if response.candidates and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content.parts:
                        for part in candidate.content.parts:
                            if hasattr(part, 'inline_data'):
                                image_data = part.inline_data.data
                                mime_type = part.inline_data.mime_type
                                
                                from ..file_processor import get_default_file_processor
                                file_processor = await get_default_file_processor()
                                file_name = f"generated_image_{uuid.uuid4().hex[:8]}.png"
                                
                                file_record = await file_processor.process_file_from_bytes(
                                    data=image_data,
                                    original_name=file_name,
                                    content_type=mime_type,
                                    metadata={
                                        "generated_by": "nano_banana",
                                        "prompt": prompt.encode('utf-8').decode('ascii', 'ignore'),
                                    },
                                    tags=["generated", "nano_banana"],
                                    public=True,
                                )
                                
                                generated_file_ids.append(file_record.file_id)
                                logger.info(f"✅ Сгенерировано изображение: {file_record.file_id}")
            
            return generated_file_ids
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации изображений: {e}")
            logger.error(f"❌ Тип ошибки: {type(e)}")
            if hasattr(e, 'response'):
                logger.error(f"❌ Ответ API: {e.response}")
            raise


class NanoBananaClientFactory:
    """Фабрика для создания Nano Banana клиентов"""
    
    @staticmethod
    def create_client() -> NanoBananaClient:
        """Создает клиент на основе конфигурации"""
        if not hasattr(settings, 'nano_banana') or not settings.nano_banana.enabled:
            raise ValueError("Nano Banana не настроен в конфигурации")
            
        if not settings.nano_banana.api_key:
            raise ValueError("API ключ Nano Banana не настроен")
            
        return NanoBananaClient(
            api_key=settings.nano_banana.api_key,
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
                logger.info("✅ Инициализирован дефолтный Nano Banana клиент")
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
