"""
LLM с встроенным биллингом для OpenRouter.
Поддерживает multimodal output: images, audio, files.
Наследуется от BaseChatModel для полного контроля над обработкой response.
"""

import logging
import base64
import httpx
from typing import Optional, List, Any, Mapping
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun

from app.core.context import get_context
from app.services.billing_service import BillingService
from app.models.billing_models import UsageType
from app.exceptions import TariffError, BillingError
from app.core.file_processor import get_default_file_processor
from app.core.audio_processor import get_default_audio_processor
from app.models import FileRecord, AudioRecord

logger = logging.getLogger(__name__)


class ChatOpenAIWithBilling(BaseChatModel):
    """
    LLM с биллингом для OpenRouter и multimodal support.
    Наследуется от BaseChatModel для полного контроля.
    """
    
    api_key: str
    model: str
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.2
    max_tokens: Optional[int] = None
    timeout: int = 60
    max_retries: int = 3
    default_headers: Optional[dict] = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        self._billing_model = kwargs.get('model', 'unknown')
        self._billing_service = BillingService()
        self._bound_tools = []
        
        logger.info(f"Создана LLM с биллингом: {self._billing_model}")
    
    @property
    def _llm_type(self) -> str:
        """Тип LLM"""
        return "openrouter-chat"
    
    def _convert_messages_to_openai_format(self, messages: List[BaseMessage]) -> List[dict]:
        """Конвертирует LangChain messages в OpenAI формат"""
        openai_messages = []
        
        for message in messages:
            if isinstance(message, HumanMessage):
                role = "user"
            elif isinstance(message, AIMessage):
                role = "assistant"
            elif isinstance(message, SystemMessage):
                role = "system"
            else:
                role = "user"
            
            # Поддержка multimodal content
            if isinstance(message.content, list):
                openai_messages.append({
                    "role": role,
                    "content": message.content
                })
            else:
                openai_messages.append({
                    "role": role,
                    "content": str(message.content)
                })
        
        return openai_messages
    
    def _convert_tools_to_openrouter_format(self, tools: List[Any]) -> List[dict]:
        """
        Конвертирует LangChain tools в формат OpenRouter.
        
        Формат OpenRouter:
        {
          "type": "function",
          "function": {
            "name": "tool_name",
            "description": "...",
            "parameters": {...}
          }
        }
        """
        openrouter_tools = []
        
        for tool in tools:
            tool_dict = {
                "type": "function",
                "function": {}
            }
            
            # Получаем имя инструмента
            if hasattr(tool, 'name'):
                tool_dict["function"]["name"] = tool.name
            elif hasattr(tool, '__name__'):
                tool_dict["function"]["name"] = tool.__name__
            else:
                logger.warning(f"Tool не имеет имени: {tool}")
                continue
            
            # Получаем описание
            if hasattr(tool, 'description'):
                tool_dict["function"]["description"] = tool.description
            elif hasattr(tool, '__doc__') and tool.__doc__:
                tool_dict["function"]["description"] = tool.__doc__.strip()
            else:
                tool_dict["function"]["description"] = f"Tool {tool_dict['function']['name']}"
            
            # Получаем параметры (args_schema)
            if hasattr(tool, 'args_schema') and tool.args_schema:
                schema = tool.args_schema
                if hasattr(schema, 'model_json_schema'):
                    json_schema = schema.model_json_schema()
                    tool_dict["function"]["parameters"] = {
                        "type": "object",
                        "properties": json_schema.get("properties", {}),
                        "required": json_schema.get("required", [])
                    }
                else:
                    tool_dict["function"]["parameters"] = {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
            else:
                tool_dict["function"]["parameters"] = {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            
            openrouter_tools.append(tool_dict)
            logger.debug(f"Сконвертирован tool: {tool_dict['function']['name']}")
        
        return openrouter_tools
    
    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs) -> ChatResult:
        """Синхронная генерация (не используется в async коде)"""
        raise NotImplementedError("Используйте ainvoke для асинхронных вызовов")
    
    async def _agenerate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs) -> ChatResult:
        """Асинхронная генерация с multimodal support"""
        # Конвертируем messages
        openai_messages = self._convert_messages_to_openai_format(messages)
        
        # Подготавливаем payload
        payload = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self.temperature),
        }
        
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        
        if stop:
            payload["stop"] = stop
        
        # Добавляем tools если они есть
        if self._bound_tools:
            openrouter_tools = self._convert_tools_to_openrouter_format(self._bound_tools)
            if openrouter_tools:
                payload["tools"] = openrouter_tools
                logger.debug(f"Добавлено {len(openrouter_tools)} tools в payload")
        
        # Headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        if self.default_headers:
            headers.update(self.default_headers)
        
        # HTTP запрос к OpenRouter
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                raise ValueError(f"OpenRouter API error: {response.status_code} - {response.text}")
            
            data = response.json()
        
        # Извлекаем токены
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        
        # Обрабатываем первый choice
        if not data.get("choices"):
            raise ValueError("Нет choices в ответе OpenRouter")
        
        choice = data["choices"][0]
        message_data = choice.get("message", {})
        content = message_data.get("content", "")
        
        # Обрабатываем multimodal output
        file_descriptions = await self._process_multimodal_fields(message_data)
        
        # Добавляем описания файлов в content
        if file_descriptions:
            if content:
                content += "\n\n" + "\n".join(file_descriptions)
            else:
                content = "\n".join(file_descriptions)
        
        # Создаем AIMessage
        ai_message = AIMessage(
            content=content,
            response_metadata={
                "token_usage": usage,
                "model_name": self.model,
                "finish_reason": choice.get("finish_reason"),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            }
        )
        
        # Создаем ChatResult
        generation = ChatGeneration(message=ai_message)
        return ChatResult(generations=[generation])
    
    async def _process_multimodal_fields(self, message_data: dict) -> List[str]:
        """
        Обрабатывает multimodal fields из OpenRouter response.
        Возвращает список текстовых описаний файлов.
        """
        file_descriptions = []
        
        # 1. Обработка images
        if "images" in message_data and message_data["images"]:
            logger.info(f"Обнаружено {len(message_data['images'])} изображений в ответе LLM")
            file_processor = await get_default_file_processor()
            
            for idx, img in enumerate(message_data["images"]):
                try:
                    file_record = await self._save_image(img, file_processor)
                    file_descriptions.append(
                        file_processor.format_file_message(file_record)
                    )
                    logger.info(f"✅ Изображение {idx+1} сохранено: {file_record.file_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка сохранения изображения {idx+1}: {e}", exc_info=True)
        
        # 2. Обработка audio
        if "audio" in message_data and message_data["audio"]:
            logger.info(f"Обнаружено {len(message_data['audio'])} аудиофайлов в ответе LLM")
            audio_processor = await get_default_audio_processor()
            
            for idx, audio in enumerate(message_data["audio"]):
                try:
                    audio_record = await self._save_audio(audio, audio_processor)
                    file_descriptions.append(
                        audio_processor.format_audio_message(audio_record)
                    )
                    logger.info(f"✅ Аудио {idx+1} сохранено: {audio_record.audio_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка сохранения аудио {idx+1}: {e}", exc_info=True)
        
        # 3. Обработка files
        if "files" in message_data and message_data["files"]:
            logger.info(f"Обнаружено {len(message_data['files'])} файлов в ответе LLM")
            file_processor = await get_default_file_processor()
            
            for idx, file_data in enumerate(message_data["files"]):
                try:
                    file_record = await self._save_file(file_data, file_processor)
                    file_descriptions.append(
                        file_processor.format_file_message(file_record)
                    )
                    logger.info(f"✅ Файл {idx+1} сохранен: {file_record.file_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка сохранения файла {idx+1}: {e}", exc_info=True)
        
        # 4. Обработка video
        if "video" in message_data and message_data["video"]:
            logger.info(f"Обнаружено {len(message_data['video'])} видео в ответе LLM")
            file_processor = await get_default_file_processor()
            
            for idx, video in enumerate(message_data["video"]):
                try:
                    file_record = await self._save_video(video, file_processor)
                    file_descriptions.append(
                        file_processor.format_file_message(file_record)
                    )
                    logger.info(f"✅ Видео {idx+1} сохранено: {file_record.file_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка сохранения видео {idx+1}: {e}", exc_info=True)
        
        return file_descriptions
    
    async def ainvoke(self, input_data, config=None, **kwargs):
        """Асинхронный вызов с биллингом"""
        # Mock модели не проверяем баланс (для тестов)
        is_mock = self._billing_model.startswith("mock-")
        
        if not is_mock:
            context = get_context()
            if not context or not context.user or not context.active_company:
                raise Exception("Нет контекста для биллинга LLM")
            
            user = context.user
            company = context.active_company
            
            resource_name = f"llm:{self._billing_model}"
            
            # Проверяем доступ к ресурсу
            can_use, reason = await self._billing_service.can_use_resource(
                user, company, resource_name
            )
            if not can_use:
                if "недоступен на тарифе" in reason:
                    raise TariffError(f"Доступ к {self._billing_model} запрещен: {reason}")
                else:
                    raise BillingError(f"Доступ к {self._billing_model} запрещен: {reason}")
        else:
            context = get_context()
            user = context.user if context else None
            company = context.active_company if context else None
        
        # Выполняем запрос через _agenerate
        result = await super().ainvoke(input_data, config, **kwargs)
        
        # Извлекаем токены из response_metadata
        input_tokens = result.response_metadata.get("input_tokens", 0)
        output_tokens = result.response_metadata.get("output_tokens", 0)
        total_tokens = result.response_metadata.get("total_tokens", 0)
        
        # Получаем стоимость из конфигурации
        from app.core.config import get_settings
        settings = get_settings()
        model_config = settings.llm.models.get(self._billing_model)
        
        if model_config:
            input_cost_per_token = model_config.input_cost_per_token
            output_cost_per_token = model_config.output_cost_per_token
        else:
            input_cost_per_token = 0.00001
            output_cost_per_token = 0.00001
        
        # Рассчитываем стоимость
        input_cost = input_tokens * input_cost_per_token
        output_cost = output_tokens * output_cost_per_token
        cost = input_cost + output_cost
        
        # Записываем использование (только для не-mock моделей)
        if not is_mock and user and company:
            await self._billing_service.record_usage(
                user=user,
                company=company,
                resource_name=resource_name,
                cost=cost,
                usage_type=UsageType.LLM_REQUEST,
                metadata={
                    "model": self._billing_model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "input_cost_per_token": input_cost_per_token,
                    "output_cost_per_token": output_cost_per_token,
                }
            )
        
        if is_mock:
            logger.debug(f"Mock LLM запрос выполнен: {self._billing_model}")
        else:
            logger.info(
                f"LLM запрос выполнен: {self._billing_model}, "
                f"токены: {input_tokens}/{output_tokens}, стоимость: {cost:.4f}₽"
            )
        
        return result
    
    def bind_tools(self, tools, **kwargs):
        """
        Привязывает tools к LLM.
        Сохраняет tools для передачи в OpenRouter API.
        
        Args:
            tools: Список LangChain tools
            **kwargs: Дополнительные параметры
            
        Returns:
            Self для поддержки chain вызовов
        """
        self._bound_tools = tools if isinstance(tools, list) else [tools]
        logger.debug(f"Привязано {len(self._bound_tools)} tools к LLM {self.model}")
        return self
    
    async def _save_image(self, img_data: dict, file_processor) -> FileRecord:
        """Сохраняет изображение из LLM response"""
        # Извлекаем URL
        image_url = img_data.get('image_url', {})
        url = image_url.get('url', '')
        
        if not url.startswith('data:image'):
            raise ValueError(f"Неподдерживаемый формат изображения: {url[:100]}")
        
        # Парсим data URL: data:image/png;base64,iVBORw0KGgo...
        parts = url.split(',', 1)
        if len(parts) != 2:
            raise ValueError("Неверный формат data URL для изображения")
        
        mime_part = parts[0]
        base64_data = parts[1]
        
        # Определяем content_type и расширение
        if 'image/png' in mime_part:
            content_type, ext = 'image/png', 'png'
        elif 'image/jpeg' in mime_part or 'image/jpg' in mime_part:
            content_type, ext = 'image/jpeg', 'jpg'
        elif 'image/webp' in mime_part:
            content_type, ext = 'image/webp', 'webp'
        elif 'image/gif' in mime_part:
            content_type, ext = 'image/gif', 'gif'
        else:
            content_type, ext = 'image/png', 'png'
        
        # Декодируем base64
        image_bytes = base64.b64decode(base64_data)
        
        # Сохраняем через file_processor
        return await file_processor.process_file_from_bytes(
            data=image_bytes,
            original_name=f"generated_image.{ext}",
            content_type=content_type,
            metadata={
                "generated_by": "llm",
                "model": self._billing_model,
                "source": "multimodal_output",
            },
            tags=["generated", "llm", "image"],
            public=True,
        )
    
    async def _save_audio(self, audio_data: dict, audio_processor) -> AudioRecord:
        """Сохраняет аудио из LLM response"""
        # Извлекаем URL
        audio_url = audio_data.get('audio_url', {})
        url = audio_url.get('url', '')
        
        if not url.startswith('data:audio'):
            raise ValueError(f"Неподдерживаемый формат аудио: {url[:100]}")
        
        # Парсим data URL: data:audio/ogg;base64,...
        parts = url.split(',', 1)
        if len(parts) != 2:
            raise ValueError("Неверный формат data URL для аудио")
        
        mime_part = parts[0]
        base64_data = parts[1]
        
        # Определяем content_type и расширение
        if 'audio/ogg' in mime_part:
            content_type, ext = 'audio/ogg; codecs=opus', 'ogg'
        elif 'audio/wav' in mime_part or 'audio/wave' in mime_part:
            content_type, ext = 'audio/wave', 'wav'
        elif 'audio/mp3' in mime_part or 'audio/mpeg' in mime_part:
            content_type, ext = 'audio/mpeg', 'mp3'
        else:
            content_type, ext = 'audio/ogg; codecs=opus', 'ogg'
        
        # Декодируем base64
        audio_bytes = base64.b64decode(base64_data)
        
        # Сохраняем через audio_processor (с авто-распознаванием речи)
        return await audio_processor.process_audio_from_bytes(
            data=audio_bytes,
            original_name=f"generated_audio.{ext}",
            content_type=content_type,
            auto_recognize=True,
            metadata={
                "generated_by": "llm",
                "model": self._billing_model,
                "source": "multimodal_output",
            },
            tags=["generated", "llm", "audio"],
            public=True,
        )
    
    async def _save_file(self, file_data: dict, file_processor) -> FileRecord:
        """Сохраняет произвольный файл из LLM response"""
        # Извлекаем URL
        file_url = file_data.get('file_url', {})
        url = file_url.get('url', '')
        
        if not url.startswith('data:'):
            raise ValueError(f"Неподдерживаемый формат файла: {url[:100]}")
        
        # Парсим data URL: data:application/pdf;base64,...
        parts = url.split(',', 1)
        if len(parts) != 2:
            raise ValueError("Неверный формат data URL для файла")
        
        mime_part = parts[0]
        base64_data = parts[1]
        
        # Извлекаем content_type
        content_type = 'application/octet-stream'
        if 'data:' in mime_part:
            type_part = mime_part.replace('data:', '').split(';')[0]
            if type_part:
                content_type = type_part
        
        # Получаем имя файла (LLM должен передать filename с расширением)
        filename = file_data.get('filename')
        
        # Если filename не передан - генерируем на основе content_type
        if not filename:
            ext = 'bin'
            if 'pdf' in content_type:
                ext = 'pdf'
            elif 'json' in content_type:
                ext = 'json'
            elif 'xml' in content_type:
                ext = 'xml'
            elif 'text' in content_type:
                ext = 'txt'
            elif 'csv' in content_type:
                ext = 'csv'
            
            filename = f'generated_file.{ext}'
        
        # Декодируем base64
        file_bytes = base64.b64decode(base64_data)
        
        # Сохраняем через file_processor
        return await file_processor.process_file_from_bytes(
            data=file_bytes,
            original_name=filename,
            content_type=content_type,
            metadata={
                "generated_by": "llm",
                "model": self._billing_model,
                "source": "multimodal_output",
            },
            tags=["generated", "llm", "file"],
            public=True,
        )
    
    async def _save_video(self, video_data: dict, file_processor) -> FileRecord:
        """Сохраняет видео из LLM response"""
        # Извлекаем URL
        video_url = video_data.get('video_url', {})
        url = video_url.get('url', '')
        
        if not url.startswith('data:video'):
            raise ValueError(f"Неподдерживаемый формат видео: {url[:100]}")
        
        # Парсим data URL: data:video/mp4;base64,...
        parts = url.split(',', 1)
        if len(parts) != 2:
            raise ValueError("Неверный формат data URL для видео")
        
        mime_part = parts[0]
        base64_data = parts[1]
        
        # Определяем content_type и расширение
        if 'video/mp4' in mime_part:
            content_type, ext = 'video/mp4', 'mp4'
        elif 'video/webm' in mime_part:
            content_type, ext = 'video/webm', 'webm'
        elif 'video/quicktime' in mime_part:
            content_type, ext = 'video/quicktime', 'mov'
        else:
            content_type, ext = 'video/mp4', 'mp4'
        
        # Декодируем base64
        video_bytes = base64.b64decode(base64_data)
        
        # Сохраняем через file_processor
        return await file_processor.process_file_from_bytes(
            data=video_bytes,
            original_name=f"generated_video.{ext}",
            content_type=content_type,
            metadata={
                "generated_by": "llm",
                "model": self._billing_model,
                "source": "multimodal_output",
            },
            tags=["generated", "llm", "video"],
            public=True,
        )
