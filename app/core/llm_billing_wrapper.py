"""
LLM с встроенным биллингом для OpenRouter.
Поддерживает multimodal output: images, audio, files.
Наследуется от BaseChatModel для полного контроля над обработкой response.
"""

import logging
import base64
import json
import httpx
from typing import Optional, List, Any, Mapping
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun

from app.core.context import get_context
from app.services.billing_service import BillingService
from app.models.billing_models import UsageType
from app.exceptions import TariffError, BillingError
from app.core.file_processor import get_default_file_processor
from app.core.audio_processor import get_default_audio_processor
from app.models import FileRecord, AudioRecord
from app.core.config import get_settings
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
            if isinstance(message, ToolMessage):
                openai_messages.append({
                    "role": "tool",
                    "content": str(message.content),
                    "tool_call_id": message.tool_call_id
                })
            elif isinstance(message, HumanMessage):
                openai_messages.append({
                    "role": "user",
                    "content": message.content if isinstance(message.content, list) else str(message.content)
                })
            elif isinstance(message, AIMessage):
                msg_dict = {
                    "role": "assistant",
                    "content": message.content if isinstance(message.content, list) else str(message.content)
                }
                
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    msg_dict["tool_calls"] = [
                        {
                            "id": tc.get("id", f"call_{tc['name']}"),
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"]) if isinstance(tc["args"], dict) else tc["args"]
                            }
                        }
                        for tc in message.tool_calls
                    ]
                
                openai_messages.append(msg_dict)
            elif isinstance(message, SystemMessage):
                openai_messages.append({
                    "role": "system",
                    "content": message.content if isinstance(message.content, list) else str(message.content)
                })
            else:
                openai_messages.append({
                    "role": "user",
                    "content": str(message.content)
                })
        
        return openai_messages
    
    def _parse_tool_arguments(self, arguments: str) -> dict:
        """
        Парсит аргументы tool из JSON строки.
        
        Args:
            arguments: JSON строка с аргументами
            
        Returns:
            Словарь с аргументами
        """
        if not arguments:
            return {}
        
        if isinstance(arguments, dict):
            return arguments
        
        try:
            return json.loads(arguments)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга аргументов tool: {e}, arguments={arguments}")
            return {}
    
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
        
        # Логируем запрос
        logger.info(f"LLM запрос:\n{json.dumps(payload, ensure_ascii=False, indent=2)}")
        
        # Получаем прокси из конфигурации
        settings = get_settings()
        proxy_url = settings.proxy.get_proxy_url("https")
        
        # Логируем если прокси используется
        if proxy_url:
            logger.info(f"🌐 Используем прокси для LLM запроса: {proxy_url}")
        
        # HTTP запрос к OpenRouter
        async with httpx.AsyncClient(timeout=self.timeout, proxy=proxy_url) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                raise ValueError(f"OpenRouter API error: {response.status_code} - {response.text}")

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"❌ Ошибка парсинга JSON ответа от OpenRouter: {e}")
                logger.error(f"Ответ сервера (первые 500 символов): {response.text[:500]}...")
                raise ValueError(f"OpenRouter вернул некорректный JSON: {e}")
        
        # Логируем ответ
        logger.info(f"LLM ответ:\n{json.dumps(data, ensure_ascii=False, indent=2)}")
        
        # Обрабатываем reasoning если есть
        await self._process_reasoning(data)
        
        # Обрабатываем первый choice
        if not data.get("choices"):
            raise ValueError("Нет choices в ответе OpenRouter")
        
        choice = data["choices"][0]
        message_data = choice.get("message", {})
        content = message_data.get("content", "")
        tool_calls_data = message_data.get("tool_calls", [])
        
        # Если есть content И tool_calls - отправляем промежуточное сообщение пользователю
        if content and content.strip() and tool_calls_data:
            context = get_context()
            if context and context.interface and context.session_id:
                try:
                    from app.interfaces.base import Message
                    intermediate_msg = Message(
                        user_id=context.user.user_id if context.user else "system",
                        flow_id=context.flow_config.flow_id if context.flow_config else "unknown",
                        session_id=context.session_id,
                        content=content,
                        platform=context.platform or "web",
                        metadata={}
                    )
                    await context.interface.send_message(intermediate_msg)
                    logger.info(f"💬 Промежуточное сообщение отправлено: {content[:80]}...")
                except Exception as e:
                    logger.error(f"Ошибка отправки промежуточного сообщения: {e}", exc_info=True)
        
        # Извлекаем токены
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        
        # Обрабатываем multimodal output
        file_descriptions = await self._process_multimodal_fields(message_data)
        
        # Добавляем описания файлов в content
        if file_descriptions:
            if content:
                content += "\n\n" + "\n".join(file_descriptions)
            else:
                content = "\n".join(file_descriptions)
        
        # Обрабатываем tool_calls из OpenRouter
        tool_calls = []
        if "tool_calls" in message_data and message_data["tool_calls"]:
            for tc in message_data["tool_calls"]:
                tool_calls.append({
                    "name": tc["function"]["name"],
                    "args": self._parse_tool_arguments(tc["function"].get("arguments", "{}")),
                    "id": tc.get("id", f"call_{tc['function']['name']}"),
                    "type": "tool_call"
                })
            logger.debug(f"Получено {len(tool_calls)} tool calls от LLM")
        
        # Создаем AIMessage с tool_calls
        ai_message = AIMessage(
            content=content or "",
            tool_calls=tool_calls if tool_calls else [],
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
    
    async def _process_reasoning(self, response_data: dict):
        """
        Обрабатывает reasoning из OpenRouter response и отправляет в интерфейс.
        
        Поддерживает множество форматов reasoning от разных провайдеров:
        - reasoning_details[] с различными типами (reasoning.text, reasoning.summary и т.д.)
        - прямое поле reasoning в message
        - любые другие форматы через универсальный парсер
        
        Args:
            response_data: Полный ответ от OpenRouter API
        """
        logger.info("🔍 _process_reasoning: начало обработки")
        
        if not response_data.get("choices"):
            logger.info("🔍 _process_reasoning: нет choices в ответе")
            return
        
        choice = response_data["choices"][0]
        message = choice.get("message", {})
        
        # Получаем контекст
        context = get_context()
        if not context:
            logger.warning("💭 Reasoning пропущен: нет контекста")
            return
            
        if not context.interface:
            logger.warning(f"💭 Reasoning пропущен: нет интерфейса в контексте (context есть, session={context.session_id})")
            return
        
        if not context.session_id:
            logger.warning("💭 Reasoning пропущен: нет session_id в контексте")
            return
        
        logger.info(f"🔍 _process_reasoning: context.interface={type(context.interface).__name__}, session_id={context.session_id}")
        
        # Проверяем настройки flow
        if context.flow_config:
            enable_reasoning = getattr(context.flow_config, 'enable_reasoning', False)
            logger.info(f"🔍 _process_reasoning: flow_config.enable_reasoning={enable_reasoning}")
            if not enable_reasoning:
                logger.warning(f"💭 Reasoning отключен в настройках flow {context.flow_config.flow_id}")
                return
        else:
            logger.info("🔍 _process_reasoning: нет flow_config в контексте, reasoning разрешен")
        
        reasoning_texts = []
        
        # 1. Проверяем reasoning_details (xAI, Gemini и др.)
        reasoning_details = message.get("reasoning_details")
        if reasoning_details and isinstance(reasoning_details, list):
            logger.info(f"🔍 _process_reasoning: найдено {len(reasoning_details)} reasoning блоков")
            
            for detail in reasoning_details:
                if not isinstance(detail, dict):
                    continue
                
                detail_type = detail.get("type", "unknown")
                reasoning_text = None
                
                # Известные типы
                if detail_type == "reasoning.text":
                    reasoning_text = detail.get("text")
                elif detail_type == "reasoning.summary":
                    reasoning_text = detail.get("summary")
                elif detail_type == "reasoning.content":
                    reasoning_text = detail.get("content")
                else:
                    # Для неизвестных типов пробуем извлечь из любого текстового поля
                    for field in ["text", "summary", "content", "reasoning", "thought"]:
                        if field in detail and isinstance(detail[field], str):
                            reasoning_text = detail[field]
                            logger.info(f"🔍 Извлечено reasoning из неизвестного типа '{detail_type}' через поле '{field}'")
                            break
                
                if reasoning_text and reasoning_text.strip():
                    reasoning_texts.append((detail_type, reasoning_text))
        
        # 2. Проверяем прямое поле reasoning в message (OpenAI o1, Claude и др.)
        if "reasoning" in message and isinstance(message["reasoning"], str):
            reasoning_text = message["reasoning"]
            if reasoning_text.strip():
                reasoning_texts.append(("reasoning", reasoning_text))
                logger.info("🔍 Найдено прямое поле 'reasoning' в message")
        
        # 3. Проверяем другие возможные поля (thinking, thought и т.д.)
        for field_name in ["thinking", "thought", "explanation"]:
            if field_name in message and isinstance(message[field_name], str):
                reasoning_text = message[field_name]
                if reasoning_text.strip():
                    reasoning_texts.append((field_name, reasoning_text))
                    logger.info(f"🔍 Найдено поле '{field_name}' в message")
        
        # Отправляем все найденные reasoning блоки
        if not reasoning_texts:
            logger.info("🔍 _process_reasoning: reasoning не найден ни в одном формате")
            return
        
        for source_type, reasoning_text in reasoning_texts:
            try:
                await context.interface.send_reasoning(
                    context.session_id, 
                    reasoning_text
                )
                logger.info(f"💭 Reasoning отправлен (тип: {source_type}): {reasoning_text[:50]}...")
            except Exception as e:
                logger.error(f"Ошибка отправки reasoning: {e}", exc_info=True)

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
