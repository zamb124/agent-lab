"""
Nano Banana клиент для генерации изображений через OpenRouter.
Использует LLM с multimodal support вместо прямого обращения к Google.

АДАПТИРОВАНО: убраны зависимости от app/*, используется только core/*
"""

import json
import logging
import base64
import re
from typing import List, Optional, TYPE_CHECKING

from core.config import get_settings
from core.files.s3_client import S3ClientFactory
from core.clients.llm.factory import get_llm

if TYPE_CHECKING:
    from core.db.storage import Storage

logger = logging.getLogger(__name__)


class NanoBananaClient:
    """
    Клиент для генерации изображений через OpenRouter.
    Использует LLM с multimodal support.
    """
    
    def __init__(
        self,
        storage: "Storage",
        model_name: str = "google/gemini-2.5-flash-preview-image",
        timeout: int = 60,
    ):
        """
        Args:
            storage: Storage для работы с БД
            model_name: Имя модели для генерации
            timeout: Таймаут запросов
        """
        self._storage = storage
        self._model_name = model_name
        self._timeout = timeout
        self._llm = None
    
    def _get_llm(self):
        """Получает LLM с multimodal support"""
        if self._llm is None:
            self._llm = get_llm(model_name=self._model_name)
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
            reference_file_ids: ID файлов-референсов
            num_images: Количество изображений
            is_editing: Режим редактирования
            
        Returns:
            Список file_id сгенерированных изображений
        """
        logger.info(f"Генерация {num_images} изображений через LLM: {prompt[:50]}...")
        
        content = []
        
        if is_editing and reference_file_ids:
            content.append({
                "type": "text",
                "text": """CRITICAL: PHOTO EDITING TASK - ABSOLUTE PROHIBITION ON GENERATION

**YOU ARE FORBIDDEN FROM:**
- Generating a NEW person (different face, body, identity, gender)
- Creating a NEW background or scene
- Generating a NEW image from scratch

**YOU MUST:**
- EDIT the EXISTING BASE IMAGE (Image #1) ONLY
- PRESERVE the EXACT person, face, body, pose, background
- ADD the product to the EXISTING person in the BASE IMAGE"""
            })
        
        if reference_file_ids:
            logger.info(f"Добавляем {len(reference_file_ids)} референсных изображений")
            
            for idx, file_id in enumerate(reference_file_ids):
                file_key = f"file:{file_id}"
                file_data_json = await self._storage.get(file_key)
                
                if not file_data_json:
                    logger.warning(f"Файл {file_id} не найден")
                    continue
                
                file_data = json.loads(file_data_json)
                
                s3_client = S3ClientFactory.create_client_for_bucket(file_data['s3_bucket'])
                try:
                    file_bytes = await s3_client.download_bytes(file_data['s3_key'])
                finally:
                    await s3_client.close()
                
                if file_bytes:
                    base64_data = base64.b64encode(file_bytes).decode('utf-8')
                    
                    if is_editing and idx == 0:
                        content.append({
                            "type": "text",
                            "text": """BASE IMAGE TO EDIT (Image #1) - DO NOT GENERATE NEW IMAGE

**THIS IS THE EXISTING PHOTOGRAPH - YOU MUST EDIT IT, NOT REPLACE IT**"""
                        })
                    
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{file_data['content_type']};base64,{base64_data}"
                        }
                    })
                    
                    logger.info(f"Добавлено изображение {file_id} (индекс {idx})")
        
        content.append({"type": "text", "text": prompt})
        
        llm = self._get_llm()
        
        response = await llm.ainvoke([{
            "role": "user",
            "content": content
        }])
        
        file_pattern = r'file_([a-f0-9]{12})'
        file_ids = re.findall(file_pattern, response.content)
        file_ids = [f"file_{fid}" for fid in file_ids]
        
        if file_ids:
            logger.info(f"Сгенерировано {len(file_ids)} изображений: {file_ids}")
        else:
            logger.warning("Не удалось найти file_id в ответе LLM")
        
        return file_ids


class NanoBananaClientFactory:
    """Фабрика для создания Nano Banana клиентов"""
    
    @staticmethod
    def create_client(storage: "Storage") -> NanoBananaClient:
        """Создает клиент на основе конфигурации"""
        settings = get_settings()
        
        if not settings.nano_banana.enabled:
            raise ValueError("Nano Banana не настроен в конфигурации")
        
        return NanoBananaClient(
            storage=storage,
            model_name=settings.nano_banana.model_name,
            timeout=settings.nano_banana.timeout,
        )




