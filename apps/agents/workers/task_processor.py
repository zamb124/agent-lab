"""
Простой воркер для выполнения задач из БД.
"""

import asyncio
from datetime import datetime, timezone

from apps.agents.config import get_agents_settings
settings = get_agents_settings()
from core.logging import setup_logging, get_logger
from apps.agents.container import get_agents_container, initialize_agents_container
from apps.agents.models import TaskStatus, SessionStatus
from core.context import set_context, clear_context, get_context
from core.db.database import create_tables, get_session_factory
from apps.agents.interfaces.base import Message
from apps.agents.exceptions import TariffError, BillingError
from apps.agents.agents.base import AgentInterrupt
from langchain_core.messages import HumanMessage, AIMessage
from apps.agents.services.state_manager import get_state_manager
from apps.agents.services.tracing.decorators import trace_span
from apps.agents.models.trace_models import SpanType
from apps.agents.services.tracing.callback_factory import get_callbacks_for_agent
from opentelemetry import trace

logger = get_logger(__name__)


class TaskProcessor:
    """Воркер для обработки задач"""

    def __init__(self):
        self._container = None
        self.running = False

    @property
    def container(self):
        """Ленивая инициализация контейнера агентов"""
        if self._container is None:
            self._container = initialize_agents_container(
                db_url=settings.database.url,
                shared_db_url=settings.database.shared_url
            )
        return self._container

    @property
    def agent_factory(self):
        return self.container.agent_factory

    @property
    def task_repository(self):
        return self.container.task_repository

    @property
    def session_repository(self):
        return self.container.session_repository

    @property
    def flow_repository(self):
        return self.container.flow_repository

    @property
    def interface_factory(self):
        return self.container.interface_factory

    async def start(self):
        """Запуск воркера"""
        logger.info("🔄 Запуск воркера задач...")

        logger.info("📊 Создание таблиц БД...")
        await create_tables(
            db_url=settings.database.url,
            table_names=["storage", "variables", "tasks", "stores", "agent_states", "otel_spans"]
        )
        if settings.database.shared_url:
            await create_tables(
                db_url=settings.database.shared_url,
                table_names=["users", "storage"]
            )
        logger.info("✅ Таблицы БД созданы")

        logger.info("🔄 Инициализация системного контейнера...")
        self.container._session_factory = await get_session_factory()
        logger.info("✅ Системный контейнер инициализирован")

        logger.info("🔄 Инициализация checkpointer...")

        self.running = True
        logger.info(f"✅ Воркер готов к работе (интервал опроса: {settings.worker.task_poll_interval}сек)")
        logger.info("🔍 Начинаем цикл обработки задач...")

        iteration = 0
        while self.running:
            try:
                iteration += 1
                logger.debug(f"🔄 Итерация #{iteration}")
                await self._process_pending_tasks()
                logger.debug(f"✅ Итерация #{iteration} завершена, ожидание {settings.worker.task_poll_interval}сек")
                await asyncio.sleep(settings.worker.task_poll_interval)
            except Exception as e:
                logger.error(f"❌ Ошибка в воркере (итерация #{iteration}): {e}", exc_info=True)
                await asyncio.sleep(settings.worker.task_poll_interval)

    async def stop(self):
        """Остановка воркера"""
        logger.info("⏹️ Остановка воркера...")
        self.running = False

    async def _process_pending_tasks(self):
        """Обработка задач в статусе pending"""
        logger.debug(f"🔍 Ищем pending задачи (limit={settings.worker.max_workers})...")
        tasks = await self.task_repository.list_pending(limit=settings.worker.max_workers)

        if not tasks:
            logger.debug("📋 Нет задач для обработки")
            return

        logger.info(f"📋 Найдено {len(tasks)} задач для обработки")
        for task in tasks:
            logger.info(f"  - {task.task_id}: flow={task.flow_id}, status={task.status}, session={task.session_id}")

        # Обрабатываем задачи параллельно
        await asyncio.gather(
            *[self._process_single_task(task) for task in tasks], return_exceptions=True
        )

    async def _process_single_task(self, task):
        """Обработка одной задачи"""
        user_msg = task.input_data.get("message", "")
        logger.info(
            f"📨 {task.task_id}: '{user_msg[:50]}' | {task.context.user.name} → {task.flow_id}"
        )

        set_context(task.context)

        try:
            await self._process_task_core(task)
        except AgentInterrupt as interrupt:
            await self._handle_agent_interrupt(task, interrupt)
        except TariffError as e:
            logger.warning(f"🎯 {task.task_id} TariffError: {e}")
            await self._handle_task_error(
                task, e,
                "Данная функция недоступна на вашем тарифном плане. Обратитесь к администратору для обновления тарифа."
            )
        except BillingError as e:
            logger.warning(f"🎯 {task.task_id} BillingError: {e}")
            await self._handle_task_error(
                task, e,
                "Прошу прощения, сейчас в сервисе технические проблемы связанные с биллингом. Попробуйте позже или обратитесь к администратору."
            )
        except ValueError as e:
            err_text = str(e)
            if "OpenRouter API error: 402" in err_text or "Insufficient credits" in err_text:
                logger.error(f"❌ {task.task_id} ошибка OpenRouter 402: {e}")
                await self._handle_task_error(
                    task, e,
                    "Недостаточно кредитов для LLM. Обратитесь к администратору, чтобы пополнить баланс, и повторите попытку."
                )
            else:
                logger.error(f"❌ {task.task_id} ValueError: {e}", exc_info=True)
                await self._handle_task_error(task, e)
        except Exception as e:
            logger.error(f"❌ {task.task_id} неожиданная ошибка: {e}", exc_info=True)
            await self._handle_task_error(task, e)
        finally:
            clear_context()

    @trace_span(
        name="task_processor.process_task",
        span_type=SpanType.OTHER,
        metadata={
            "component": "task_processor",
            "operation": "process_task"
        }
    )
    async def _process_task_core(self, task):
        """Основная логика обработки задачи"""
        self._setup_tracing(task)
        interface = await self._setup_interface(task)
        
        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.now(timezone.utc)
        await self.task_repository.set(task)

        if hasattr(task, 'skip_agent') and task.skip_agent:
            await self._handle_skip_agent(task, interface)
            return

        flow_config = await self._get_flow_config(task.flow_id)
        entry_agent = await self.agent_factory.get_agent(flow_config.entry_point_agent)
        config = {"configurable": {"thread_id": task.session_id}}
        user_message = self._extract_user_message(task)
        
        await self._setup_flow_variables(flow_config)
        self._setup_callbacks(config)

        result = await self._execute_agent(entry_agent, task.session_id, user_message, config)
        
        if "__interrupt__" in result:
            await self._handle_interrupt(task, result, interface)
            return

        await self._complete_task(task, result, user_message, interface, config)

    def _setup_tracing(self, task):
        """Настраивает трейсинг для задачи"""
        current_span = trace.get_current_span()
        if not current_span:
            return
            
        current_span.set_attribute("task_id", task.task_id)
        current_span.set_attribute("flow_id", task.flow_id)
        current_span.set_attribute("session_id", task.session_id)
        current_span.set_attribute("platform", task.context.platform)
        current_span.set_attribute("user_msg", task.input_data.get("message", ""))
        
        if task.context and task.context.user:
            current_span.set_attribute("user_id", task.context.user.user_id)
        if task.context and task.context.active_company:
            current_span.set_attribute("company_id", task.context.active_company.company_id)

    async def _setup_interface(self, task):
        """Настраивает интерфейс для задачи"""
        platform = task.context.platform
        
        if platform in ("migration", "system"):
            return None
        
        interface_factory = get_agents_container().interface_factory
        metadata = task.input_data.get("metadata", {})
        
        if platform == "telegram":
            metadata["flow_id"] = task.flow_id

        interface = await interface_factory.create_interface(platform, metadata)

        current_context = get_context()
        if current_context and interface:
            current_context.interface = interface

        if interface:
            await interface.start_typing_indicator(task.session_id)
            
        return interface

    async def _handle_skip_agent(self, task, interface):
        """Обрабатывает задачу с skip_agent=True"""
        response_text = task.input_data.get("message", "")
        task.status = TaskStatus.COMPLETED
        task.output_data = {"message": response_text, "skipped_agent": True}
        task.completed_at = datetime.now(timezone.utc)
        await self.task_repository.set(task)

        await self._update_session_stats(task.session_id, response_text)
        await self._set_session_active(task.session_id, task.context.platform)
        
        if interface:
            await interface.stop_typing_indicator(task.session_id)

        result = {"messages": [AIMessage(content=response_text)]}
        await self._send_result_via_interface(task, result)

    async def _get_flow_config(self, flow_id):
        """Получает конфигурацию flow"""
        flow_config = await self.flow_repository.get(flow_id)
        if not flow_config:
            current_context = get_context()
            company_id = current_context.active_company.company_id if current_context and current_context.active_company else 'НЕТ'
            raise ValueError(f"Flow {flow_id} не найден в БД (контекст: company={company_id})")
        return flow_config

    async def _setup_flow_variables(self, flow_config):
        """Настраивает переменные flow в контексте"""
        current_context = get_context()
        if not current_context:
            return
            
        if hasattr(flow_config, 'variables') and flow_config.variables:
            variables_service = get_agents_container().variables_service
            resolved_variables = await variables_service.resolve(flow_config.variables)
            current_context.flow_variables = resolved_variables
            logger.debug(f"📝 Переменные flow установлены: {list(resolved_variables.keys())}")

    def _setup_callbacks(self, config):
        """Настраивает callbacks для трейсинга"""
        callbacks = get_callbacks_for_agent()
        if callbacks:
            if "callbacks" not in config:
                config["callbacks"] = []
            config["callbacks"].extend(callbacks)

    def _extract_user_message(self, task):
        """Извлекает сообщение пользователя из задачи"""
        if "tool_call" in task.input_data:
            tool_call_info = task.input_data["tool_call"]
            tool_name = tool_call_info["tool_name"]
            tool_args = tool_call_info.get("tool_args", {})
            logger.info(f"📋 {task.task_id}: отложенный вызов тула {tool_name}")
            return f"Выполнить отложенную задачу: {tool_name} с аргументами {tool_args}"
        return task.input_data.get("message", "")

    async def _execute_agent(self, entry_agent, session_id, user_message, config):
        """Выполняет агента с учетом восстановления после interrupt"""
        state_manager = await get_state_manager()
        saved_state = await state_manager.get_or_create_session(session_id)
        
        if not saved_state.get("messages"):
            return await entry_agent.ainvoke(
                {"messages": [HumanMessage(content=user_message)], "task_id": config.get("task_id", ""), "session_id": session_id},
                config=config
            )
        
        saved_state["messages"].append(HumanMessage(content=user_message))
        return await entry_agent.ainvoke(saved_state, config=config)

    async def _handle_agent_interrupt(self, task, interrupt):
        """Обрабатывает AgentInterrupt исключение"""
        interface = await self._setup_interface(task)
        
        if interface:
            await interface.stop_typing_indicator(task.session_id)

        task.status = TaskStatus.WAITING_FOR_INPUT
        task.output_data = {
            "status": "waiting_for_input",
            "question": str(interrupt.value),
            "interrupt_data": str(interrupt),
        }
        await self.task_repository.set(task)

        await self._update_session_stats(task.session_id, task.input_data.get("message", ""))
        await self._set_session_waiting_input(task.session_id, task.context.platform)
        await self._send_result_via_interface(task, str(interrupt.value))

    async def _handle_interrupt(self, task, result, interface):
        """Обрабатывает interrupt в результате выполнения агента"""
        interrupt_value = self._extract_interrupt_value(result["__interrupt__"])
        
        task.status = TaskStatus.WAITING_FOR_INPUT
        task.output_data = {
            "status": "waiting_for_input",
            "question": interrupt_value,
            "interrupt_data": str(result["__interrupt__"]),
        }
        await self.task_repository.set(task)

        await self._update_session_stats(task.session_id, task.input_data.get("message", ""))
        await self._set_session_waiting_input(task.session_id, task.context.platform)
        await self._send_result_via_interface(task, interrupt_value)

    def _extract_interrupt_value(self, interrupts):
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

    async def _complete_task(self, task, result, user_message, interface, config):
        """Завершает задачу и отправляет результат"""
        task.status = TaskStatus.COMPLETED
        task.output_data = result if isinstance(result, dict) else {"result": str(result)}
        task.completed_at = datetime.now(timezone.utc)
        await self.task_repository.set(task)

        if task.execute_at:
            await self._mark_delayed_task_as_executed(task.task_id, config)

        await self._update_session_stats(task.session_id, user_message)
        await self._set_session_active(task.session_id, task.context.platform)
        
        if interface:
            await interface.stop_typing_indicator(task.session_id)

        await self._send_result_via_interface(task, result)

    async def _handle_task_error(self, task, error: Exception, user_message: str = None):
        """Обработка ошибки задачи"""
        interface = await self._setup_interface(task)
        if interface:
            await interface.stop_typing_indicator(task.session_id)

        message_to_user = user_message or "Произошла ошибка при обработке запроса. Попробуйте позже или обратитесь к администратору."
        await self._send_error_message_to_user(task, message_to_user)

        task.status = TaskStatus.FAILED
        task.error_message = str(error)
        task.completed_at = datetime.now(timezone.utc)
        await self.task_repository.set(task)
        await self._set_session_active(task.session_id, task.context.platform)

    async def _set_session_active(self, session_id: str, platform: str):
        """Возвращает сессию в статус ACTIVE (если она не закрыта)"""
        session_config = await self.session_repository.get(session_id)

        if not session_config:
            logger.warning(f"Сессия {session_id} не найдена для возврата в ACTIVE")
            return

        if session_config.status in [SessionStatus.EXPIRED, SessionStatus.INACTIVE]:
            logger.info(
                f"Сессия {session_id} в финальном статусе {session_config.status.value}, не активируем"
            )
            return

        session_config.status = SessionStatus.ACTIVE
        session_config.last_activity = datetime.now(timezone.utc)
        await self.session_repository.set(session_config)
        logger.info(f"Сессия {session_id} возвращена в статус ACTIVE")

    async def _set_session_waiting_input(self, session_id: str, platform: str):
        """Переводит сессию в статус WAITING_INPUT"""
        session_config = await self.session_repository.get(session_id)

        if not session_config:
            logger.warning(f"Сессия {session_id} не найдена для перевода в WAITING_INPUT")
            return

        session_config.status = SessionStatus.WAITING_INPUT
        session_config.last_activity = datetime.now(timezone.utc)
        await self.session_repository.set(session_config)
        logger.info(f"Сессия {session_id} переведена в WAITING_INPUT")

    async def _mark_delayed_task_as_executed(self, task_id: str, config):
        """Помечает отложенную задачу как executed в сессионной памяти"""
        session_id = config.get("configurable", {}).get("thread_id") if config else None
        if not session_id:
            return
        
        state_manager = await get_state_manager()
        state = await state_manager.get_or_create_session(session_id)
        
        if "store" in state and "delayed_tasks" in state["store"]:
            tasks = state["store"]["delayed_tasks"]
            if task_id in tasks:
                tasks[task_id]["status"] = "executed"
                tasks[task_id]["executed_at"] = datetime.now(timezone.utc).isoformat()
                await state_manager.save_session(state)
                logger.info(f"✅ Задача {task_id} помечена как executed в сессионной памяти")
            else:
                logger.debug(f"⚠️ Задача {task_id} не найдена в delayed_tasks сессии")
        else:
            logger.debug(f"⚠️ В state нет delayed_tasks для пометки задачи {task_id}")

    async def _update_session_stats(self, session_id: str, user_message: str):
        """Обновляет статистику сессии: message_count и first_message"""
        session_config = await self.session_repository.get(session_id)

        if not session_config:
            logger.warning(f"Сессия {session_id} не найдена для обновления статистики")
            return

        session_config.message_count += 2

        if not session_config.first_message and user_message:
            preview = user_message[:100] if len(user_message) > 100 else user_message
            session_config.first_message = preview

        await self.session_repository.set(session_config)
        logger.debug(f"Статистика сессии обновлена: {session_config.message_count} сообщений")

    async def _send_error_message_to_user(self, task, error_message: str):
        """Отправляет сообщение об ошибке пользователю"""
        platform = task.platform
        
        if platform in ("migration", "system"):
            logger.debug(f"⏭️ Пропускаем отправку ошибки для системной платформы {platform}")
            return
        
        metadata = task.input_data.get("metadata", {})

        config = {**metadata, "flow_id": task.flow_id}
        interface = await self.interface_factory.create_interface(platform, config)

        if interface is None:
            logger.error("❌ Не удалось создать интерфейс для отправки ошибки")
            return

        error_response = Message(
            user_id=task.user_id,
            flow_id=task.flow_id,
            session_id=task.session_id,
            content=error_message,
            platform=task.platform,
            metadata=metadata,
        )

        await interface.send_message(error_response)
        logger.info("✅ Отправлено сообщение об ошибке пользователю")

    async def _send_result_via_interface(self, task, result):
        """Отправляет результат через соответствующий интерфейс платформы"""
        platform = task.platform
        
        if platform in ("migration", "system"):
            logger.debug(f"⏭️ Пропускаем отправку результата для системной платформы {platform}")
            return
        
        metadata = task.input_data.get("metadata", {})

        config = {**metadata, "flow_id": task.flow_id}
        interface = await self.interface_factory.create_interface(platform, config)

        if interface is None:
            # Для API или если интерфейс не нужен
            logger.info(f"📤 Результат сохранен в БД для платформы {task.platform}")
            return

        # Извлекаем текст ответа
        if isinstance(result, dict) and "messages" in result:
            messages = result["messages"]
            if messages:
                last_message = messages[-1]
                if hasattr(last_message, "content"):
                    response_text = last_message.content
                else:
                    response_text = str(last_message)
            else:
                response_text = "Нет ответа"
        else:
            response_text = str(result)

        # Создаем сообщение и отправляем
        response_message = Message(
            user_id=task.user_id,
            flow_id=task.flow_id,
            session_id=task.session_id,
            content=response_text,
            platform=task.platform,
            metadata=metadata,
        )

        await interface.send_message(response_message)
        logger.info(
            f"📤 {task.task_id}: '{response_text[:80]}{'...' if len(response_text) > 80 else ''}' → {task.platform}"
        )


async def main():
    """Главная функция воркера"""
    processor = TaskProcessor()

    try:
        await processor.start()
    except KeyboardInterrupt:
        logger.info("⏹️ Получен сигнал остановки")
        await processor.stop()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка воркера: {e}")
        raise


if __name__ == "__main__":
    # Настройка логирования
    setup_logging("agents", settings.logging)

    logger.info("🚀 Запуск Task Processor...")
    asyncio.run(main())
