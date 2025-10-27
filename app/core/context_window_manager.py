"""
Менеджер контекстного окна для управления размером диалога и автосуммаризации.
Интегрируется с LangGraph checkpointer для обновления истории сообщений.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage

from app.core.config import get_settings
from app.core.llm_factory import get_llm
from app.core.context import get_context
from app.core.checkpointer import get_checkpointer
from app.interfaces.base import Message

logger = logging.getLogger(__name__)


class ContextWindowManager:
    """Управление размером контекстного окна с автосуммаризацией"""
    
    def __init__(self):
        self.settings = get_settings()
    
    async def check_and_summarize_if_needed(
        self,
        messages: List[BaseMessage],
        llm_config: Dict[str, Any],
        config: Dict[str, Any],
        update_checkpoint: bool = True
    ) -> Tuple[List[BaseMessage], bool]:
        """
        Проверяет размер контекста и суммаризирует если нужно.
        
        Args:
            messages: Текущий список сообщений
            llm_config: Конфигурация LLM агента (из AgentConfig.llm_config)
            config: RunnableConfig для LangGraph (с thread_id и т.д.)
            
        Returns:
            (messages, was_summarized) - обновленные сообщения и флаг суммаризации
        """
        logger.info(f"🔍 check_and_summarize_if_needed вызван: {len(messages)} сообщений")
        logger.info(f"🔍 llm_config: {llm_config}")
        
        if not llm_config.get("enable_auto_summarization", True):
            logger.info("❌ Автосуммаризация отключена в конфигурации агента")
            return messages, False
        
        model_name = llm_config.get("model", self.settings.llm.default_model)
        logger.info(f"🔍 Модель: {model_name}")
        
        max_tokens = self._get_context_window(model_name, llm_config)
        current_tokens = self._count_tokens(messages)
        threshold = llm_config.get("summarization_threshold", 0.8)
        threshold_tokens = int(max_tokens * threshold)
        
        logger.info(
            f"📊 Проверка контекста: {current_tokens}/{max_tokens} токенов "
            f"(порог {threshold*100:.0f}% = {threshold_tokens} токенов)"
        )
        
        if current_tokens <= threshold_tokens:
            logger.info(
                f"Контекст в норме: {current_tokens}/{max_tokens} токенов "
                f"(порог {threshold_tokens})"
            )
            return messages, False
        
        logger.info(
            f"🔄 Контекст превысил порог: {current_tokens}/{max_tokens} токенов "
            f"({threshold*100:.0f}% порог = {threshold_tokens})"
        )
        
        await self._notify_user_about_summarization(config)
        
        target_ratio = llm_config.get("summarization_target", 0.2)
        target_tokens = int(max_tokens * target_ratio)
        
        summarized_messages = await self._summarize_messages(
            messages=messages,
            target_tokens=target_tokens,
            llm_config=llm_config
        )
        
        # Если суммаризация не изменила messages - возвращаем False
        if len(summarized_messages) == len(messages):
            logger.info("Суммаризация пропущена (недостаточно сообщений)")
            return messages, False
        
        logger.info(
            f"✅ Суммаризация завершена: {len(messages)} → {len(summarized_messages)} сообщений, "
            f"{current_tokens} → {self._count_tokens(summarized_messages)} токенов"
        )
        
        # Обновляем checkpoint в БД если требуется
        if update_checkpoint:
            await self._update_checkpoint_messages(config, summarized_messages)
        
        return summarized_messages, True
    
    def _get_context_window(self, model_name: str, llm_config: Dict[str, Any]) -> int:
        """
        Получает размер контекстного окна модели.
        
        Приоритет:
        1. llm_config.context_window (из AgentConfig)
        2. settings.llm.models[model_name].context_window (из conf.json)
        
        Если не найдено - бросает исключение (требуется настройка в conf.json)
        """
        if llm_config.get("context_window"):
            return llm_config["context_window"]
        
        logger.info(f"🔍 Доступные модели в settings: {list(self.settings.llm.models.keys())}")
        
        model_config = self.settings.llm.models.get(model_name)
        logger.info(f"🔍 model_config для '{model_name}': {model_config}")
        
        if model_config:
            logger.info(f"🔍 context_window из model_config: {model_config.context_window}")
            if model_config.context_window:
                return model_config.context_window
        
        raise ValueError(
            f"Размер контекстного окна для модели '{model_name}' не найден! "
            f"Добавьте 'context_window' для этой модели в conf.json или в llm_config агента."
        )
    
    def _count_tokens(self, messages: List[BaseMessage]) -> int:
        """
        Подсчет токенов в сообщениях.
        
        Используется консервативная оценка: 1 токен ≈ 2.5 символа.
        Это более точная оценка с учетом:
        - Накладных расходов на форматирование OpenAI API
        - Специальных токенов (role, разделители)
        - Русского языка (больше токенов чем английский)
        """
        total_chars = 0
        message_details = []
        
        for i, msg in enumerate(messages):
            # 1. Content
            if hasattr(msg, 'content'):
                content = msg.content
                if isinstance(content, str):
                    total_chars += len(content)
                elif isinstance(content, list):
                    # Multimodal content (text + images)
                    for item in content:
                        if isinstance(item, dict):
                            if 'text' in item:
                                total_chars += len(str(item['text']))
                            if 'image_url' in item:
                                total_chars += 100  # Примерная оценка для image_url
                        else:
                            total_chars += len(str(item))
                else:
                    total_chars += len(str(content))
            
            # 2. Tool calls
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                import json
                for tc in msg.tool_calls:
                    # Считаем tool_call как JSON строку
                    tc_str = json.dumps(tc) if isinstance(tc, dict) else str(tc)
                    total_chars += len(tc_str)
            
            # 3. Additional kwargs
            if hasattr(msg, 'additional_kwargs') and msg.additional_kwargs:
                import json
                kwargs_chars = len(json.dumps(msg.additional_kwargs))
                total_chars += kwargs_chars
            
            # Сохраняем детали для логирования
            msg_type = type(msg).__name__
            msg_chars = len(str(msg.content)) if hasattr(msg, 'content') else 0
            message_details.append(f"  [{i}] {msg_type}: {msg_chars} символов")
        
        # Консервативная оценка: 1 токен ≈ 2.5 символа (вместо 4)
        # Это учитывает что OpenAI API добавляет много служебных токенов
        estimated_tokens = int(total_chars / 2.5)
        
        # Оверхед на каждое сообщение (role, форматирование, разделители)
        extra_tokens_per_message = 10  # Увеличено с 4 до 10 для учета накладных расходов
        total_messages_overhead = len(messages) * extra_tokens_per_message
        
        total_tokens = estimated_tokens + total_messages_overhead
        
        # Логируем детали подсчета
        logger.debug(f"📊 Подсчет токенов:")
        logger.debug(f"  Всего сообщений: {len(messages)}")
        logger.debug(f"  Всего символов: {total_chars}")
        logger.debug(f"  Токены (символы/4): {estimated_tokens}")
        logger.debug(f"  Оверхед: {total_messages_overhead}")
        logger.debug(f"  ИТОГО токенов: {total_tokens}")
        if len(message_details) <= 10:
            for detail in message_details:
                logger.debug(detail)
        
        return total_tokens
    
    async def _summarize_messages(
        self,
        messages: List[BaseMessage],
        target_tokens: int,
        llm_config: Dict[str, Any]
    ) -> List[BaseMessage]:
        """
        Суммаризирует messages до целевого размера.
        
        Алгоритм:
        1. Отделяем SystemMessage (не суммаризируем!)
        2. Берем последнее сообщение пользователя (HumanMessage)
        3. Суммаризируем ВСЕ остальные сообщения
        4. Возвращаем: [SystemMessages] + [Summary] + [Последнее сообщение юзера]
        """
        system_messages = [m for m in messages if isinstance(m, SystemMessage)]
        other_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        
        if len(other_messages) <= 2:
            logger.warning("Мало сообщений для суммаризации (<=2), пропускаем")
            return messages
        
        # Находим последнее сообщение от пользователя
        last_user_message = None
        for msg in reversed(other_messages):
            if isinstance(msg, HumanMessage):
                last_user_message = msg
                break
        
        if not last_user_message:
            logger.warning("Не найдено сообщение пользователя, пропускаем суммаризацию")
            return messages
        
        # Берем все сообщения ДО последнего от пользователя
        last_user_index = other_messages.index(last_user_message)
        messages_to_summarize = other_messages[:last_user_index]
        
        if not messages_to_summarize:
            logger.warning("Нет сообщений для суммаризации (только последнее от юзера)")
            return messages
        
        logger.info(
            f"Суммаризируем {len(messages_to_summarize)} сообщений, "
            f"оставляем последнее от пользователя"
        )
        
        summarization_model = self.settings.llm.default_summarization_model
        logger.info(f"Используем глобальную модель для суммаризации: {summarization_model}")
        
        summarizer_llm = get_llm(summarization_model)
        
        conversation_text = self._format_messages_for_summary(messages_to_summarize)
        
        summary_prompt = f"""Ты ассистент для краткого пересказа диалога между пользователем и ИИ агентом.

ЗАДАЧА: Суммаризируй следующий диалог, сохранив ВСЮ ключевую информацию:
- Факты о пользователе
- Результаты работы инструментов (tools)
- Важные решения и выводы
- Контекст диалога

ДИАЛОГ:
{conversation_text}

Создай краткое содержание на русском (не более {target_tokens} токенов).
Пиши от третьего лица, структурированно."""

        summary_response = await summarizer_llm.ainvoke([HumanMessage(content=summary_prompt)])
        summary_text = summary_response.content
        
        if not summary_text or not summary_text.strip():
            raise ValueError(f"LLM вернул пустую суммаризацию для модели {summarization_model}")
        
        # Возвращаем: SystemMessage + Summary + Последнее сообщение пользователя
        result = system_messages + [
            HumanMessage(content=f"📚 Краткое содержание предыдущего диалога:\n\n{summary_text}")
        ] + [last_user_message]
        
        return result
    
    def _format_messages_for_summary(self, messages: List[BaseMessage]) -> str:
        """Форматирует сообщения в текст для суммаризации"""
        lines = []
        for msg in messages:
            role = "Пользователь" if isinstance(msg, HumanMessage) else "Ассистент"
            content = str(msg.content)
            
            if len(content) > 500:
                content = content[:500] + "..."
            
            lines.append(f"[{role}]: {content}")
        
        return "\n".join(lines)
    
    async def _notify_user_about_summarization(self, config: Dict[str, Any]):
        """Уведомляет пользователя о начале суммаризации"""
        context = get_context()
        if not context or not context.interface:
            logger.debug("Нет интерфейса для уведомления о суммаризации")
            return
        
        session_id = config.get("configurable", {}).get("thread_id")
        if not session_id:
            logger.debug("Нет session_id для уведомления о суммаризации")
            return
        
        # Извлекаем user_id из session_id (формат: platform:user_id:flow_id:unique_id)
        user_id = context.user.user_id if context.user else "system"
        chat_id = None
        
        if ":" in session_id:
            parts = session_id.split(":")
            if len(parts) >= 2:
                user_id = parts[1]  # Второй элемент - user_id
                
                # Для Telegram chat_id = user_id
                if parts[0] == "telegram":
                    chat_id = user_id
        
        # Формируем metadata с chat_id для Telegram
        metadata = {"is_system": True, "type": "summarization_start"}
        if chat_id:
            metadata["chat_id"] = chat_id
        
        notification = Message(
            user_id=user_id,
            session_id=session_id,
            content="⏳ Производится суммаризация истории диалога для оптимизации контекста...",
            flow_id=context.flow_config.flow_id if context.flow_config else "system",
            platform=context.platform or "web",
            metadata=metadata
        )
        await context.interface.send_message(notification)
        
        # Показываем typing indicator чтобы юзер видел что агент работает
        await context.interface.send_typing_notification(session_id, is_typing=True)
        
        logger.info(f"📤 Отправлено уведомление о суммаризации для user_id={user_id}, session={session_id}")
    
    async def _update_checkpoint_messages(self, config: Dict[str, Any], new_messages: List[BaseMessage]):
        """
        Обновляет checkpoint в БД с новыми суммаризированными сообщениями.
        
        Args:
            config: RunnableConfig с thread_id
            new_messages: Суммаризированные сообщения
        """
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            raise ValueError("thread_id обязателен для обновления checkpoint")
        
        checkpointer = await get_checkpointer()
        
        # Получаем текущий checkpoint
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        
        if not checkpoint_tuple or not checkpoint_tuple.checkpoint:
            raise ValueError(f"Checkpoint не найден для thread_id={thread_id}")
        
        # Обновляем messages в checkpoint
        checkpoint = checkpoint_tuple.checkpoint
        if "channel_values" not in checkpoint:
            raise ValueError(f"Checkpoint для thread_id={thread_id} не содержит channel_values")
        
        if "messages" not in checkpoint["channel_values"]:
            raise ValueError(f"Checkpoint для thread_id={thread_id} не содержит messages в channel_values")
        
        old_count = len(checkpoint["channel_values"]["messages"])
        checkpoint["channel_values"]["messages"] = new_messages
        
        # ВАЖНО: Используем config из checkpoint_tuple (там есть все нужные поля)
        checkpoint_config = checkpoint_tuple.config
        
        # Сохраняем обновленный checkpoint
        await checkpointer.aput(
            config=checkpoint_config,
            checkpoint=checkpoint,
            metadata=checkpoint_tuple.metadata,
            new_versions=checkpoint_tuple.checkpoint.get("channel_versions", {})
        )
        
        logger.info(
            f"✅ Checkpoint обновлен для thread_id={thread_id}: "
            f"{old_count} → {len(new_messages)} сообщений"
        )

