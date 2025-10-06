"""
Простой воркер для выполнения задач из БД.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.core.storage import Storage
from app.core.container import get_container
from app.models import TaskStatus, SessionConfig, SessionStatus
from app.core.context import set_context, clear_context, get_context
from app.db.database import create_tables
from app.core.checkpointer import init_checkpointer
from app.interfaces.factory import InterfaceFactory
from app.interfaces.base import Message
from app.exceptions import TariffError, BillingError
from langgraph.errors import GraphInterrupt
from langchain_core.messages import HumanMessage
from langgraph.types import Command

logger = logging.getLogger(__name__)


class TaskProcessor:
    """Воркер для обработки задач"""

    def __init__(self):
        self.storage = Storage()
        container = get_container()
        self.agent_factory = container.get_agent_factory()
        self.running = False

    async def start(self):
        """Запуск воркера"""
        logger.info("🔄 Запуск воркера задач...")

        # Инициализация
        await create_tables()
        await init_checkpointer()

        self.running = True

        while self.running:
            try:
                await self._process_pending_tasks()
                await asyncio.sleep(settings.worker.task_poll_interval)
            except Exception as e:
                logger.error(f"❌ Ошибка в воркере: {e}")
                await asyncio.sleep(settings.worker.task_poll_interval)

    async def stop(self):
        """Остановка воркера"""
        logger.info("⏹️ Остановка воркера...")
        self.running = False

    async def _process_pending_tasks(self):
        """Обработка задач в статусе pending"""
        tasks = await self.storage.get_pending_tasks(limit=settings.worker.max_workers)

        if not tasks:
            return

        logger.info(f"📋 Найдено {len(tasks)} задач для обработки")

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

        interface_factory = InterfaceFactory()
        metadata = task.input_data.get("metadata", {})
        interface = await interface_factory.create_interface(task.context.platform, metadata)
        
        if interface:
            await interface.send_typing_notification(task.session_id, True)

        try:
            task.status = TaskStatus.PROCESSING
            task.started_at = datetime.now(timezone.utc)
            await self.storage.set_task_config(task)

            flow_config = await self.storage.get_flow_config(task.flow_id)
            if not flow_config:
                current_context = get_context()
                company_id = current_context.active_company.company_id if current_context and current_context.active_company else 'НЕТ'
                raise ValueError(f"Flow {task.flow_id} не найден в БД (контекст: company={company_id})")

            entry_agent = await self.agent_factory.get_agent(flow_config.entry_point_agent)

            config = {"configurable": {"thread_id": task.session_id}}
            input_data_with_context = dict(task.input_data)
            input_data_with_context["task_id"] = task.task_id
            input_data_with_context["session_id"] = task.session_id
            user_message = input_data_with_context.get("message", "")
            
            compiled_graph = await entry_agent.compile_graph()
            state = await compiled_graph.aget_state(config)
            has_pending = state.next and len(state.next) > 0
            
            if has_pending:
                logger.info(f"🔄 Возобновляем выполнение")
                result = await compiled_graph.ainvoke(Command(resume=user_message), config)
            else:
                logger.info(f"🆕 Новый запрос")
                initial_state = {
                    "messages": [HumanMessage(content=user_message)],
                    **input_data_with_context,
                }
                result = await entry_agent.ainvoke(initial_state, config=config)

            # Проверяем на interrupt в результате (как в старой архитектуре)
            logger.info(
                f"🔍 Проверяем результат на interrupt: type={type(result)}, keys={list(result.keys()) if isinstance(result, dict) else 'НЕ DICT'}"
            )

            if "__interrupt__" in result:
                logger.info("🔄 Получен interrupt в результате - граф остановлен")
                interrupts = result["__interrupt__"]

                # Извлекаем значение interrupt для API
                if interrupts:
                    if isinstance(interrupts, list) and interrupts:
                        # Если это список символов - собираем в строку
                        if all(isinstance(x, str) and len(x) == 1 for x in interrupts):
                            interrupt_value = "".join(interrupts)
                        # Если это список Interrupt объектов
                        elif hasattr(interrupts[0], "value"):
                            interrupt_value = interrupts[0].value
                        # Иначе берем первый элемент
                        else:
                            interrupt_value = str(interrupts[0])
                    else:
                        interrupt_value = str(interrupts)
                else:
                    interrupt_value = "Пользователь должен ответить"

                # Сохраняем задачу в состоянии ожидания ввода
                task.status = TaskStatus.WAITING_FOR_INPUT
                task.output_data = {
                    "status": "waiting_for_input",
                    "question": interrupt_value,
                    "interrupt_data": str(interrupts),
                }

                logger.info(f"🔄 Сохраняем задачу с interrupt: {task.task_id}")
                await self.storage.set_task_config(task)
                logger.info(f"🔄 Задача с interrupt сохранена: {task.task_id}")

                # КРИТИЧНО: Переводим сессию в WAITING_INPUT чтобы разблокировать новые сообщения
                await self._set_session_waiting_input(task.session_id, task.context.platform)

                # ВАЖНО: Отправляем вопрос пользователю через интерфейс
                logger.info(
                    f"📤 Отправляем interrupt вопрос пользователю: {interrupt_value}"
                )
                await self._send_result_via_interface(task, interrupt_value)

                return  # Выходим без завершения задачи
            else:
                logger.info(
                    "🔍 НЕТ __interrupt__ в результате, продолжаем обычное выполнение"
                )

            # Сохраняем результат
            task.status = TaskStatus.COMPLETED
            task.output_data = (
                result if isinstance(result, dict) else {"result": str(result)}
            )
            task.completed_at = datetime.now(timezone.utc)

            await self.storage.set_task_config(task)
            logger.info(f"✅ {task.task_id} завершена")

            # Возвращаем сессию в статус ACTIVE
            await self._set_session_active(task.session_id, task.context.platform)

            # Отправляем уведомление об окончании печати
            if interface:
                await interface.send_typing_notification(task.session_id, False)

            # Отправляем результат обратно пользователю через интерфейс
            await self._send_result_via_interface(task, result)

        except GraphInterrupt as interrupt:
            logger.info(f"❓ {task.task_id} ждет ответа: {interrupt.value}")
            
            if interface:
                await interface.send_typing_notification(task.session_id, False)
            
            task.status = TaskStatus.PROCESSING
            task.output_data = {
                "status": "waiting_for_input",
                "question": str(interrupt.value),
                "interrupt_data": str(interrupt),
            }
            await self.storage.set_task_config(task)
            await self._set_session_waiting_input(task.session_id, task.context.platform)
            await self._send_result_via_interface(task, str(interrupt.value))
            return
            
        except TariffError as e:
            logger.warning(f"🎯 {task.task_id} TariffError: {e}")
            await self._handle_task_error(
                task, e, interface,
                user_message="Данная функция недоступна на вашем тарифном плане. Обратитесь к администратору для обновления тарифа."
            )
            
        except BillingError as e:
            logger.warning(f"🎯 {task.task_id} BillingError: {e}")
            await self._handle_task_error(
                task, e, interface,
                user_message="Прошу прощения, сейчас в сервисе технические проблемы связанные с биллингом. Попробуйте позже или обратитесь к администратору."
            )
            
        except Exception as e:
            logger.error(f"❌ {task.task_id} неожиданная ошибка: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            await self._handle_task_error(task, e, interface)
        finally:
            clear_context()

    async def _handle_task_error(self, task, error: Exception, interface, user_message: str = None):
        """Обработка ошибки задачи"""
        if interface:
            await interface.send_typing_notification(task.session_id, False)
            await asyncio.sleep(0.1)
        
        if user_message:
            await self._send_error_message_to_user(task, user_message)
        
        task.status = TaskStatus.FAILED
        task.error_message = str(error)
        task.completed_at = datetime.now(timezone.utc)
        await self.storage.set_task_config(task)
        await self._set_session_active(task.session_id, task.context.platform)
    
    async def _set_session_active(self, session_id: str, platform: str):
        """Возвращает сессию в статус ACTIVE (если она не закрыта)"""
        session_key = f"session:{session_id}"
        session_data = await self.storage.get(session_key)

        if session_data:
            session_config = SessionConfig.model_validate_json(session_data)
            
            # Не активируем сессии в финальных статусах
            if session_config.status in [SessionStatus.EXPIRED, SessionStatus.INACTIVE]:
                logger.info(
                    f"⚠️ Сессия {session_id} в финальном статусе {session_config.status.value}, не активируем"
                )
                return
            
            session_config.status = SessionStatus.ACTIVE
            session_config.last_activity = datetime.now(timezone.utc)
            await self.storage.set(session_key, session_config.model_dump_json())
            logger.info(f"✅ Сессия {session_id} возвращена в статус ACTIVE")
        else:
            logger.warning(f"⚠️ Сессия {session_id} не найдена для возврата в ACTIVE")

    async def _set_session_waiting_input(self, session_id: str, platform: str):
        """Переводит сессию в статус WAITING_INPUT"""
        session_key = f"session:{session_id}"
        session_data = await self.storage.get(session_key)

        if session_data:
            session_config = SessionConfig.model_validate_json(session_data)
            session_config.status = SessionStatus.WAITING_INPUT
            session_config.last_activity = datetime.now(timezone.utc)
            await self.storage.set(session_key, session_config.model_dump_json())
            logger.info(f"🔄 Сессия {session_id} переведена в WAITING_INPUT")
        else:
            logger.warning(f"Сессия {session_id} не найдена для перевода в WAITING_INPUT")

    async def _send_error_message_to_user(self, task, error_message: str):
        """Отправляет сообщение об ошибке пользователю"""
        factory = InterfaceFactory()
        metadata = task.input_data.get("metadata", {})
        
        interface = await factory.create_interface(task.platform, metadata)

        if interface is None:
            logger.error(f"❌ Не удалось создать интерфейс для отправки ошибки")
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
        logger.info(f"✅ Отправлено сообщение об ошибке пользователю")

    async def _send_result_via_interface(self, task, result):
        """Отправляет результат через соответствующий интерфейс платформы"""
        # Создаем интерфейс для платформы
        factory = InterfaceFactory()
        metadata = task.input_data.get("metadata", {})

        interface = await factory.create_interface(task.platform, metadata)

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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("🚀 Запуск Task Processor...")
    asyncio.run(main())
