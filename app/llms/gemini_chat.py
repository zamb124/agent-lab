"""
Нативная интеграция Google Gemini с LangChain
"""

import logging
from typing import Any, Dict, List, Optional
import google.generativeai as genai
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.tools import BaseTool
from pydantic import Field

logger = logging.getLogger(__name__)


class GeminiChatModel(BaseChatModel):
    """Нативная интеграция Google Gemini с LangChain"""
    
    api_key: str = Field()
    model_name: str = Field(default="gemini-1.5-flash")
    temperature: float = Field(default=0.2)
    max_tokens: Optional[int] = Field(default=None)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Настраиваем клиент Gemini
        genai.configure(api_key=self.api_key)
        # Используем object.__setattr__ для обхода Pydantic валидации
        object.__setattr__(self, '_gemini_model', genai.GenerativeModel(self.model_name))
        
        logger.info(f"GeminiChatModel создан: модель={self.model_name}, температура={self.temperature}")
    
    def _convert_messages_to_gemini(self, messages: List[BaseMessage]) -> str:
        """Конвертирует LangChain сообщения в формат Gemini"""
        
        # Объединяем все сообщения в один текст без префиксов
        parts = []
        
        for message in messages:
            if isinstance(message, SystemMessage):
                parts.append(message.content)
            elif isinstance(message, HumanMessage):
                parts.append(f"Пользователь: {message.content}")
            elif isinstance(message, AIMessage):
                if message.content.strip():  # Только если есть контент
                    parts.append(message.content)
            else:
                if message.content.strip():
                    parts.append(message.content)
        
        return "\n\n".join(parts)
    
    def _generate(self, messages: List[BaseMessage], stop=None, run_manager=None, **kwargs):
        """Синхронная генерация"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._agenerate(messages, stop, run_manager, **kwargs))
        except RuntimeError:
            return asyncio.run(self._agenerate(messages, stop, run_manager, **kwargs))
    
    async def _agenerate(self, messages: List[BaseMessage], stop=None, run_manager=None, **kwargs):
        """Асинхронная генерация"""
        
        # Конвертируем сообщения
        prompt = self._convert_messages_to_gemini(messages)
        
        try:
            # Настройки генерации
            generation_config = genai.types.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            )
            
            # Подготавливаем параметры для генерации
            generate_kwargs = {
                "generation_config": generation_config
            }
            
            # Добавляем инструменты если есть
            if hasattr(self, '_gemini_tools') and self._gemini_tools:
                # Создаем tools в формате Gemini
                tools = [genai.protos.Tool(function_declarations=self._gemini_tools)]
                generate_kwargs["tools"] = tools
            
            # Генерируем ответ
            response = await self._gemini_model.generate_content_async(
                prompt,
                **generate_kwargs
            )
            
            # Обрабатываем ответ
            if response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]
                
                # Проверяем есть ли function call
                if hasattr(part, 'function_call') and part.function_call:
                    # Обрабатываем function call
                    function_call = part.function_call
                    
                    # Создаем AIMessage с tool_calls в формате LangChain
                    message = AIMessage(
                        content="",
                        tool_calls=[{
                            "name": function_call.name,
                            "args": dict(function_call.args),
                            "id": f"call_{function_call.name}",
                            "type": "tool_call"
                        }]
                    )
                else:
                    # Обычный текстовый ответ
                    message = AIMessage(content=response.text)
            else:
                message = AIMessage(content="")
            
            generation = ChatGeneration(message=message)
            return ChatResult(generations=[generation])
            
        except Exception as e:
            logger.error(f"Ошибка Gemini API: {e}")
            raise
    
    @property
    def _llm_type(self) -> str:
        return "gemini"
    
    def bind_tools(self, tools, **kwargs):
        """Привязывает инструменты к модели (для ReAct агентов)"""
        # Сохраняем инструменты и конвертируем их в формат Gemini
        object.__setattr__(self, '_tools', tools)
        object.__setattr__(self, '_gemini_tools', self._convert_tools_to_gemini(tools))
        logger.info(f"bind_tools: привязано {len(tools)} инструментов")
        return self
    
    def _convert_tools_to_gemini(self, tools: List[BaseTool]) -> List[Dict[str, Any]]:
        """Конвертирует LangChain инструменты в формат Gemini"""
        
        gemini_tools = []
        
        for tool in tools:
            # Получаем схему инструмента
            tool_schema = tool.args_schema
            
            # Создаем function declaration для Gemini согласно документации
            function_declaration = genai.protos.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={},
                    required=[]
                )
            )
            
            # Конвертируем параметры если есть схема
            properties = {}
            required = []
            
            if tool_schema:
                if hasattr(tool_schema, 'model_fields'):
                    # Pydantic v2 style
                    for field_name, field_info in tool_schema.model_fields.items():
                        properties[field_name] = genai.protos.Schema(
                            type=self._python_type_to_gemini_type(field_info.annotation),
                            description=field_info.description or f"Parameter {field_name}"
                        )
                        if field_info.is_required():
                            required.append(field_name)
            
            # Обновляем parameters
            function_declaration.parameters.properties.update(properties)
            function_declaration.parameters.required.extend(required)
            
            gemini_tools.append(function_declaration)
        
        return gemini_tools
    
    def _python_type_to_gemini_type(self, python_type):
        """Конвертирует Python тип в Gemini Type"""
        if python_type == str:
            return genai.protos.Type.STRING
        elif python_type == int:
            return genai.protos.Type.INTEGER
        elif python_type == float:
            return genai.protos.Type.NUMBER
        elif python_type == bool:
            return genai.protos.Type.BOOLEAN
        elif python_type == list:
            return genai.protos.Type.ARRAY
        elif python_type == dict:
            return genai.protos.Type.OBJECT
        else:
            return genai.protos.Type.STRING  # Дефолт
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
