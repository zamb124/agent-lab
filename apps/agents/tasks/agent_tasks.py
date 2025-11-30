"""
TaskIQ задачи для обработки сообщений агентами.

Миграция логики из TaskProcessor в TaskIQ tasks.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage

from core.tasks.broker import broker
from core.context import set_context, clear_context, get_context
from core.models.context_models import Context
from core.models import User, Company

from apps.agents.container import get_agents_container
from apps.agents.models import SessionStatus
from apps.agents.exceptions import TariffError, BillingError, AgentInterrupt
from apps.agents.services.state_manager import get_state_manager
from apps.agents.services.tracing.callback_factory import get_callbacks_for_agent
from apps.agents.tasks.message_tasks import send_message_task

logger = logging.getLogger(__name__)


@broker.task(retry_on_error=True, max_retries=3)
async def process_agent_task(
    flow_id: str,
    session_id: str,
    message: str,
    platform: str,
    user_id: str,
    company_id: str,
    metadata: Dict[str, Any],
    user_data: Optional[Dict[str, Any]] = None,
    company_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Обработка сообщения агентом.
    
    Args:
        flow_id: ID flow для обработки
        session_id: ID сессии
        message: Текст сообщения пользователя
        platform: Платформа (web, telegram, whatsapp, api)
        user_id: ID пользователя
        company_id: ID компании
        metadata: Дополнительные данные (chat_id, bot_token и т.д.)
        user_data: Данные пользователя для контекста
        company_data: Данные компании для контекста
    
    Returns:
        Dict с результатом выполнения
    """
    container = get_agents_container()
    
    # Восстанавливаем контекст
    context = _build_context(
        user_id, company_id, session_id, platform, 
        user_data, company_data, metadata
    )
    set_context(context)
    
    try:
        # Получаем flow config
        flow_repo = container.flow_repository
        flow_config = await flow_repo.get(flow_id)
        if not flow_config:
            raise ValueError(f"Flow {flow_id} не найден в БД (company={company_id})")
        
        # Получаем агента
        agent_factory = container.agent_factory
        entry_agent = await agent_factory.get_agent(flow_config.entry_point_agent)
        
        # Настраиваем flow variables
        await _setup_flow_variables(flow_config, container)
        
        # Настраиваем конфиг для агента
        config = {"configurable": {"session_id": session_id}}
        callbacks = get_callbacks_for_agent()
        if callbacks:
            config["callbacks"] = callbacks
        
        # Выполняем агента
        result = await _execute_agent(entry_agent, session_id, message, config)
        
        # Обрабатываем interrupt
        if "__interrupt__" in result:
            interrupt_value = _extract_interrupt_value(result["__interrupt__"])
            
            # Отправляем interrupt сообщение через TaskIQ
            await send_message_task.kiq(
                platform=platform,
                flow_id=flow_id,
                session_id=session_id,
                content=interrupt_value,
                metadata=metadata,
                user_id=user_id,
            )
            
            # Обновляем статус сессии
            await _set_session_waiting_input(session_id, container)
            
            return {
                "status": "waiting_for_input",
                "question": interrupt_value,
                "session_id": session_id,
            }
        
        # Извлекаем ответ
        response_text = _extract_response_text(result)
        
        # Отправляем ответ через TaskIQ
        await send_message_task.kiq(
            platform=platform,
            flow_id=flow_id,
            session_id=session_id,
            content=response_text,
            metadata=metadata,
            user_id=user_id,
        )
        
        # Обновляем статус сессии
        await _set_session_active(session_id, container)
        await _update_session_stats(session_id, message, container)
        
        return {
            "status": "completed",
            "session_id": session_id,
            "response": response_text,
        }
        
    except AgentInterrupt as interrupt:
        logger.info(f"AgentInterrupt для session {session_id}: {interrupt.value}")
        
        await _send_message_direct(
            platform=platform,
            flow_id=flow_id,
            session_id=session_id,
            content=str(interrupt.value),
            metadata=metadata,
            user_id=user_id,
        )
        
        await _set_session_waiting_input(session_id, container)
        
        return {
            "status": "waiting_for_input",
            "question": str(interrupt.value),
            "session_id": session_id,
        }
        
    except TariffError as e:
        logger.warning(f"TariffError для session {session_id}: {e}")
        error_msg = "Данная функция недоступна на вашем тарифном плане."
        await _send_error_message(platform, flow_id, session_id, error_msg, metadata, user_id)
        raise
        
    except BillingError as e:
        logger.warning(f"BillingError для session {session_id}: {e}")
        error_msg = "Технические проблемы с биллингом. Попробуйте позже."
        await _send_error_message(platform, flow_id, session_id, error_msg, metadata, user_id)
        raise
        
    except ValueError as e:
        if "OpenRouter API error: 402" in str(e) or "Insufficient credits" in str(e):
            logger.error(f"OpenRouter 402 для session {session_id}: {e}")
            error_msg = "Недостаточно кредитов для LLM. Обратитесь к администратору."
            await _send_error_message(platform, flow_id, session_id, error_msg, metadata, user_id)
        raise
        
    finally:
        clear_context()


def _build_context(
    user_id: str,
    company_id: str,
    session_id: str,
    platform: str,
    user_data: Optional[Dict],
    company_data: Optional[Dict],
    metadata: Dict,
) -> Context:
    """Восстанавливает контекст из сериализованных данных"""
    user = User(
        user_id=user_id,
        name=user_data.get("name", "User") if user_data else "User",
        companies={company_id: user_data.get("groups", ["user"])} if user_data else {company_id: ["user"]},
        active_company_id=company_id,
    )
    
    company = Company(
        company_id=company_id,
        name=company_data.get("name", "Company") if company_data else "Company",
        subdomain=company_data.get("subdomain", company_id) if company_data else company_id,
        is_active=True,
    )
    
    return Context(
        user=user,
        session_id=session_id,
        platform=platform,
        active_company=company,
        user_companies=[company],
        metadata=metadata,
    )


async def _setup_flow_variables(flow_config, container):
    """Настраивает переменные flow в контексте"""
    context = get_context()
    if not context:
        return
        
    if hasattr(flow_config, 'variables') and flow_config.variables:
        variables_service = container.variables_service
        resolved_variables = await variables_service.resolve(flow_config.variables)
        context.flow_variables = resolved_variables


async def _execute_agent(entry_agent, session_id: str, message: str, config: dict):
    """Выполняет агента с учетом восстановления после interrupt"""
    state_manager = await get_state_manager()
    saved_state = await state_manager.get_or_create_session(session_id)
    
    if not saved_state.get("messages"):
        return await entry_agent.ainvoke(
            {"messages": [HumanMessage(content=message)], "session_id": session_id},
            config=config
        )
    
    saved_state["messages"].append(HumanMessage(content=message))
    return await entry_agent.ainvoke(saved_state, config=config)


def _extract_interrupt_value(interrupts) -> str:
    """Извлекает значение interrupt из результата"""
    if not interrupts:
        return "Пользователь должен ответить"
        
    if isinstance(interrupts, list) and interrupts:
        if all(isinstance(x, str) and len(x) == 1 for x in interrupts):
            return "".join(interrupts)
        if hasattr(interrupts[0], "value"):
            return interrupts[0].value
        return str(interrupts[0])
        
    return str(interrupts)


def _extract_response_text(result) -> str:
    """Извлекает текст ответа из результата агента"""
    if isinstance(result, dict) and "messages" in result:
        messages = result["messages"]
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, "content"):
                return last_message.content
            return str(last_message)
        return "Нет ответа"
    return str(result)


async def _set_session_active(session_id: str, container):
    """Возвращает сессию в статус ACTIVE"""
    session_repo = container.session_repository
    session_config = await session_repo.get(session_id)
    
    if not session_config:
        return
    
    if session_config.status in [SessionStatus.EXPIRED, SessionStatus.INACTIVE]:
        return
    
    session_config.status = SessionStatus.ACTIVE
    session_config.last_activity = datetime.now(timezone.utc)
    await session_repo.set(session_config)


async def _set_session_waiting_input(session_id: str, container):
    """Переводит сессию в статус WAITING_INPUT"""
    session_repo = container.session_repository
    session_config = await session_repo.get(session_id)
    
    if not session_config:
        return
    
    session_config.status = SessionStatus.WAITING_INPUT
    session_config.last_activity = datetime.now(timezone.utc)
    await session_repo.set(session_config)


async def _update_session_stats(session_id: str, user_message: str, container):
    """Обновляет статистику сессии"""
    session_repo = container.session_repository
    session_config = await session_repo.get(session_id)
    
    if not session_config:
        return
    
    session_config.message_count += 2
    
    if not session_config.first_message and user_message:
        preview = user_message[:100] if len(user_message) > 100 else user_message
        session_config.first_message = preview
    
    await session_repo.set(session_config)




async def _send_message_direct(
    platform: str,
    flow_id: str,
    session_id: str,
    content: str,
    metadata: Dict,
    user_id: str,
):
    """Отправляет сообщение напрямую через интерфейс"""
    from apps.agents.tasks.message_tasks import send_message_task
    # Вызываем функцию напрямую, не через .kiq()
    await send_message_task(
        platform=platform,
        flow_id=flow_id,
        session_id=session_id,
        content=content,
        metadata=metadata,
        user_id=user_id,
    )


async def _send_error_message(
    platform: str,
    flow_id: str,
    session_id: str,
    error_msg: str,
    metadata: Dict,
    user_id: str,
):
    """Отправляет сообщение об ошибке пользователю"""
    await _send_message_direct(
        platform=platform,
        flow_id=flow_id,
        session_id=session_id,
        content=error_msg,
        metadata=metadata,
        user_id=user_id,
    )

