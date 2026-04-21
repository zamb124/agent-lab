"""
A2AChannel - реализация A2A протокола.

Полная поддержка A2A спецификации через a2a-sdk.
Поддержка evaluation через metadata.evaluation.test_case_id.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from a2a.types import (
    Artifact,
    DataPart,
    DeleteTaskPushNotificationConfigParams,
    GetTaskPushNotificationConfigParams,
    ListTaskPushNotificationConfigParams,
    Message,
    MessageSendParams,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskIdParams,
    TaskPushNotificationConfig,
    TaskQueryParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.utils.message import get_message_text, new_agent_text_message

from apps.flows.src.channels.base import BaseChannel
from apps.flows.src.channels.types import PreparedTaskParams
from apps.flows.src.container import get_container
from apps.flows.src.state.cancellation import CANCEL_KEY_TTL
from core.context import set_current_channel
from apps.flows.config import settings
from apps.flows.src.evaluation.service import EvaluationService
from apps.flows.src.files import extract_incoming_a2a_files, format_a2a_files_content
from core.logging import get_logger
from apps.flows.src.services.push_notifications import dict_to_config
from apps.flows.src.streaming import Emitter
from core.state import ExecutionState
from apps.flows.src.streaming.subscriber import EventSubscriber, StreamEvent
from apps.idle_worker.tasks.push_notification_tasks import (
    delete_config,
    get_config,
    list_configs,
    send_task_update,
    set_config,
)
from apps.flows.src.utils import extract_json_from_response

logger = get_logger(__name__)


def _get_evaluation_metadata(metadata: Optional[Dict]) -> Optional[Dict]:
    """Извлекает параметры evaluation из metadata."""
    if not metadata:
        return None
    return metadata.get("evaluation")


async def _build_task_from_events(
    events: List[StreamEvent],
    task_id: str,
    context_id: str,
    input_message: Message,
    flow_id: str,
) -> Task:
    """
    Строит Task из накопленных событий.

    Извлекает artifacts, status, response из событий и формирует Task по A2A SDK.
    Разделяет артефакты по именам (response vs reasoning).
    Загружает существующую историю из state для multi-turn сценариев.
    """
    artifacts_dict: Dict[str, Artifact] = {}
    final_status: Optional[TaskStatus] = None
    response_parts: List[str] = []
    reasoning_parts: List[str] = []

    for event in events:
        if isinstance(event, TaskArtifactUpdateEvent):
            if event.artifact:
                artifact_name = event.artifact.name or "response"
                for part in event.artifact.parts:
                    if hasattr(part.root, "text"):
                        if artifact_name == "reasoning":
                            if event.append:
                                reasoning_parts.append(part.root.text)
                            else:
                                reasoning_parts = [part.root.text]
                        elif artifact_name == "response":
                            if event.append:
                                response_parts.append(part.root.text)
                            else:
                                response_parts = [part.root.text]
        elif isinstance(event, TaskStatusUpdateEvent):
            if event.final:
                final_status = event.status

    response_text = "".join(response_parts)
    if not response_text and final_status and final_status.message and final_status.message.parts:
        response_text = "".join(
            part.root.text
            for part in final_status.message.parts
            if hasattr(part.root, "text")
        )

    if reasoning_parts:
        reasoning_text = "".join(reasoning_parts)
        artifacts_dict["reasoning"] = Artifact(
            artifactId=str(uuid.uuid4()),
            name="reasoning",
            parts=[Part(root=TextPart(text=reasoning_text))],
        )

    # Проверяем есть ли JSON в ответе
    json_data = extract_json_from_response(response_text)

    # Создаем response artifact:
    # 1. Для JSON данных - как DataPart (всегда создаем если найден JSON)
    # 2. Для текстовых ответов - только если есть reasoning (чтобы разделить reasoning и response)
    if json_data is not None:
        artifacts_dict["response"] = Artifact(
            artifactId=str(uuid.uuid4()),
            name="response",
            parts=[Part(root=DataPart(data={"res": json.dumps(json_data, ensure_ascii=False)}))],
        )
    elif response_text and reasoning_parts:
        artifacts_dict["response"] = Artifact(
            artifactId=str(uuid.uuid4()),
            name="response",
            parts=[Part(root=TextPart(text=response_text))],
        )

    artifacts = list(artifacts_dict.values())

    if final_status is None:
        final_status = TaskStatus(
            state=TaskState.completed,
            message=new_agent_text_message(response_text) if response_text else None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # Загружаем существующую историю из state для multi-turn сценариев
    container = get_container()
    session_id = f"{flow_id}:{context_id}"
    state = await container.state_manager.get_state(session_id)
    existing_history = state.get("messages", []) if state else []

    # Устанавливаем task_id в input_message для истории
    history_message = input_message.model_copy(update={"task_id": task_id})

    # Для existing_history устанавливаем task_id если его нет
    for msg in existing_history:
        if hasattr(msg, "task_id") and not msg.task_id:
            msg.task_id = task_id

    history = existing_history + [history_message]

    if response_text and final_status.state == TaskState.completed:
        agent_message = new_agent_text_message(response_text)
        agent_message.task_id = task_id
        history.append(agent_message)
    elif final_status.state == TaskState.input_required and final_status.message:
        agent_message = final_status.message
        if not agent_message.task_id:
            agent_message = agent_message.model_copy(update={"task_id": task_id})
        history.append(agent_message)

    # Когда есть artifacts (response/reasoning), не дублируем ответ в status.message
    # Исключение: input_required - там message содержит вопрос к пользователю
    if artifacts and final_status.message and final_status.state != TaskState.input_required:
        timestamp = final_status.timestamp or datetime.now(timezone.utc).isoformat()
        final_status = TaskStatus(
            state=final_status.state,
            timestamp=timestamp,
            message=None,
        )

    return Task(
        id=task_id,
        contextId=context_id,
        status=final_status,
        artifacts=artifacts if artifacts else None,
        history=history,
    )


class A2AChannel(BaseChannel):
    """
    A2A канал коммуникации.

    Полная реализация A2A протокола через a2a-sdk.
    """

    name = "a2a"

    async def send_to_user(
        self,
        content: str,
        buttons: Optional[List[str]] = None,
        attachments: Optional[List[Any]] = None,
    ) -> None:
        """
        Отправляет сообщение пользователю через A2A.

        В A2A это делается через emit событий в Redis Pub/Sub.
        """
        if not self.context:
            logger.warning("Cannot send_to_user: no context available")
            return

        container = get_container()
        task_id = self.context.metadata.get("task_id", "")
        context_id = self.context.metadata.get("context_id", "")
        session_id = self._generate_session_id(context_id)

        exec_state = ExecutionState(
            task_id=task_id,
            context_id=context_id,
            session_id=session_id,
            user_id=self.context.user.user_id if self.context.user else "system",
            user_groups=self._get_user_groups_from_context(self.context)
        )
        emitter = Emitter(container.redis_client, exec_state)
        await emitter.emit_text_chunk(content, append=False, last_chunk=True)

    async def _handle_takeover_user_reply(
        self,
        prepared: PreparedTaskParams,
    ) -> AsyncGenerator[Union[TaskStatusUpdateEvent], None]:
        """A2A Section 3.4.3: follow-up при input-required с operator takeover.

        Маршрутизирует текст пользователя в dialog_log без запуска flow.
        Возвращает status-update input-required (задача остаётся в ожидании оператора).
        """
        container = get_container()
        svc = container.operator_handoff_service

        file_ids: list[str] = []
        if prepared.files_data:
            for fd in prepared.files_data:
                fid = fd.get("file_id")
                if fid:
                    file_ids.append(str(fid))
                    continue
                path = fd.get("path")
                if path and str(path).startswith(("http://", "https://")):
                    continue
                if path:
                    raise ValueError(
                        "Вложение A2A без file_id: ожидается персист через API (S3), "
                        "локальные path в state.files не поддерживаются."
                    )

        await svc.receive_user_reply(
            company_id=self.context.active_company.company_id,
            task_id=prepared.takeover_operator_task_id,
            text=prepared.content,
            user_id=prepared.user_id,
            file_ids=file_ids if file_ids else None,
        )
        logger.info(
            "[on_message_stream] takeover user-reply routed to dialog_log, "
            "task_id=%s, operator_task=%s",
            prepared.task_id,
            prepared.takeover_operator_task_id,
        )
        yield TaskStatusUpdateEvent(
            taskId=prepared.task_id,
            contextId=prepared.context_id,
            status=TaskStatus(
                state=TaskState.input_required,
                message=new_agent_text_message(prepared.content),
            ),
            final=True,
        )

    async def _persist_incoming_a2a_files(self, message: Message) -> tuple[List[Dict[str, Any]], str]:
        """Байты FileWithBytes -> S3 + FileRecord; FileWithUri -> только path в state."""
        incoming = extract_incoming_a2a_files(message)
        if not incoming:
            return [], ""

        if not self.context or not self.context.active_company:
            raise ValueError(
                "Загрузка вложений A2A требует active_company в контексте запроса"
            )

        company_id = self.context.active_company.company_id
        user_id = self.context.user.user_id if self.context.user else None
        prefix = f"/{settings.server.name}/api/v1/files/download"
        container = get_container()
        files_data: List[Dict[str, Any]] = []

        for inc in incoming:
            if inc.data is not None:
                item = await container.file_processor.persist_uploaded_file_as_state_files_item(
                    data=inc.data,
                    original_name=inc.name,
                    content_type=inc.mime_type,
                    uploaded_by=user_id,
                    company_id=company_id,
                    public=False,
                    download_url_prefix=prefix,
                )
                files_data.append(item)
            else:
                if not inc.uri:
                    raise ValueError("FileWithUri без uri")
                files_data.append(
                    {
                        "name": inc.name,
                        "path": inc.uri,
                        "mime_type": inc.mime_type,
                        "size": inc.size,
                    }
                )

        return files_data, format_a2a_files_content(files_data)

    async def _prepare_a2a_params(self, params: MessageSendParams):
        """Подготовка параметров специфичных для A2A."""
        message = params.message
        content = get_message_text(message)

        files_data, files_content_suffix = await self._persist_incoming_a2a_files(message)
        if files_content_suffix:
            content += files_content_suffix

        prepared = await self._prepare_task_params(
            content=content,
            context_id=message.context_id,
            task_id=message.task_id,
            message=message,
            metadata=params.metadata,
            files_data=files_data,
        )

        return prepared

    async def on_message_send(
        self, params: MessageSendParams, context: Any = None
    ) -> Union[Task, Message]:
        """
        Синхронное выполнение - кикает task и собирает события через collect().

        Поддерживает evaluation через metadata.evaluation:
        - test_case_id: ID тест-кейса для запуска

        ВАЖНО: подписка на канал ПЕРЕД киком задачи, иначе race condition -
        события могут быть опубликованы до подписки и потеряны.

        Args:
            params: параметры сообщения
            context: контекст с user_groups для проверки permissions
        """
        set_current_channel(self)

        # Проверяем evaluation mode
        eval_metadata = _get_evaluation_metadata(params.metadata)
        if eval_metadata and eval_metadata.get("test_case_id"):
            # Собираем все события и формируем Task
            events = [event async for event in self._run_evaluation(params, eval_metadata)]
            return await _build_task_from_events(
                events=events,
                task_id=str(uuid.uuid4()),
                context_id=params.message.context_id or str(uuid.uuid4()),
                input_message=params.message,
                flow_id=self.flow_id,
            )

        # Обычный режим
        skill_id = "default"
        if params.metadata and "skill" in params.metadata:
            skill_id = params.metadata["skill"]

        user_groups = self._get_user_groups_from_context(context)
        await self.check_permissions(user_groups, skill_id)

        prepared = await self._prepare_a2a_params(params)

        # A2A Section 3.4.3: follow-up при активном operator takeover
        if prepared.is_takeover_user_reply:
            events = [event async for event in self._handle_takeover_user_reply(prepared)]
            return await _build_task_from_events(
                events=events,
                task_id=prepared.task_id,
                context_id=prepared.context_id,
                input_message=params.message,
                flow_id=self.flow_id,
            )

        container = get_container()

        # Таймаут короче для тестов
        from core.config.testing import is_testing
        timeout = 30.0 if is_testing() else 300.0

        subscriber = EventSubscriber(container.redis_client)
        ready_event = asyncio.Event()

        async def collect_with_subscription():
            return await subscriber.collect(prepared.task_id, timeout=timeout, ready_event=ready_event)

        collect_task = asyncio.create_task(collect_with_subscription())

        await ready_event.wait()

        logger.debug(f"[A2A] Subscribed to stream:{prepared.task_id}, kicking task")
        await self.create_task(prepared)

        events = await collect_task

        logger.debug(f"[A2A] Collected {len(events)} events for task {prepared.task_id}")

        return await _build_task_from_events(
            events=events,
            task_id=prepared.task_id,
            context_id=prepared.context_id,
            input_message=prepared.message,
            flow_id=self.flow_id,
        )

    async def _run_evaluation(
        self,
        params: MessageSendParams,
        eval_metadata: Dict,
    ) -> AsyncGenerator[Union[TaskStatusUpdateEvent, TaskArtifactUpdateEvent], None]:
        """
        Запускает evaluation тест через EvaluationService и yield'ит A2A события.

        A2A канал только конвертирует события сервиса в A2A формат.
        Вся логика тестирования в EvaluationService.
        """
        container = get_container()
        test_case_id = eval_metadata["test_case_id"]

        skill_id = "default"
        if params.metadata and "skill" in params.metadata:
            skill_id = params.metadata["skill"]

        task_id = str(uuid.uuid4())
        context_id = params.message.context_id or str(uuid.uuid4())

        service = container.evaluation_service

        try:
            async for event in service.run_test_stream(
                self.flow_id, skill_id, test_case_id, task_id=task_id
            ):
                event_type = event.get("type")

                if event_type == "error":
                    raise ValueError(event["message"])

                elif event_type == "start":
                    yield TaskArtifactUpdateEvent(
                        taskId=task_id,
                        contextId=context_id,
                        artifact=Artifact(
                            artifactId=str(uuid.uuid4()),
                            name="response",
                            parts=[
                                Part(root=TextPart(text=f"🧪 Запуск теста: {test_case_id}\n\n"))
                            ],
                        ),
                        append=False,
                        lastChunk=False,
                    )

                elif event_type == "user":
                    text = f"👤 **USER**: {event['content']}\n"
                    yield TaskArtifactUpdateEvent(
                        taskId=task_id,
                        contextId=context_id,
                        artifact=Artifact(
                            artifactId=str(uuid.uuid4()),
                            name="response",
                            parts=[Part(root=TextPart(text=text))],
                        ),
                        append=True,
                        lastChunk=False,
                    )

                elif event_type == "assistant":
                    text = f"🤖 **ASSISTANT**: {event['content']}\n\n"
                    yield TaskArtifactUpdateEvent(
                        taskId=task_id,
                        contextId=context_id,
                        artifact=Artifact(
                            artifactId=str(uuid.uuid4()),
                            name="response",
                            parts=[Part(root=TextPart(text=text))],
                        ),
                        append=True,
                        lastChunk=False,
                    )

                elif event_type == "result":
                    status_icon = "" if event["status"] == "passed" else "❌"
                    result_text = f"\n---\n{status_icon} **Результат**: {event['status'].upper()}"
                    result_text += f"\n⏱Время: {event['duration_ms']}ms"
                    if event.get("turns_count", 0) > 0:
                        result_text += f"\n💬 Ходов: {event['turns_count']}"
                    if event.get("error"):
                        result_text += f"\n⚠️ Ошибка: {event['error']}"

                    # task_id для трейсинга
                    eval_task_id = event.get("task_id")
                    if eval_task_id:
                        result_text += f"\nTask ID: {eval_task_id}"

                    yield TaskArtifactUpdateEvent(
                        taskId=task_id,
                        contextId=context_id,
                        artifact=Artifact(
                            artifactId=str(uuid.uuid4()),
                            name="response",
                            parts=[Part(root=TextPart(text=result_text))],
                        ),
                        append=True,
                        lastChunk=True,
                    )

                    # Для evaluation тестов всегда completed - passed/failed это результат теста, а не ошибка
                    yield TaskStatusUpdateEvent(
                        taskId=task_id,
                        contextId=context_id,
                        status=TaskStatus(state=TaskState.completed),
                        final=True,
                    )

        except Exception as e:
            logger.exception(f"Error running evaluation test {test_case_id}")

            yield TaskArtifactUpdateEvent(
                taskId=task_id,
                contextId=context_id,
                artifact=Artifact(
                    artifactId=str(uuid.uuid4()),
                    name="response",
                    parts=[Part(root=TextPart(text=f"❌ Ошибка теста: {str(e)}"))],
                ),
                append=True,
                lastChunk=True,
            )
            yield TaskStatusUpdateEvent(
                taskId=task_id,
                contextId=context_id,
                status=TaskStatus(state=TaskState.failed),
                final=True,
            )

    async def on_message_stream(
        self, params: MessageSendParams, context: Any = None
    ) -> AsyncGenerator[Union[Message, Task, TaskStatusUpdateEvent, TaskArtifactUpdateEvent], None]:
        """
        Streaming выполнение - yield'ит события по мере генерации через Redis Pub/Sub.

        Поддерживает evaluation через metadata.evaluation:
        - test_case_id: ID тест-кейса для запуска

        ВАЖНО: подписка на канал ПЕРЕД киком задачи, иначе race condition.

        A2A input-required follow-up (Section 3.4.3):
        при активном operator takeover реплика пользователя маршрутизируется в dialog_log
        без запуска flow; SSE отдаёт единственный status-update input-required.

        Args:
            params: параметры сообщения
            context: контекст с user_groups для проверки permissions
        """
        set_current_channel(self)

        # Проверяем evaluation mode
        eval_metadata = _get_evaluation_metadata(params.metadata)
        if eval_metadata and eval_metadata.get("test_case_id"):
            async for event in self._run_evaluation(params, eval_metadata):
                yield event
            return

        # Обычный режим
        skill_id = "default"
        if params.metadata and "skill" in params.metadata:
            skill_id = params.metadata["skill"]

        user_groups = self._get_user_groups_from_context(context)
        await self.check_permissions(user_groups, skill_id)

        logger.info(f"[on_message_stream] Starting for flow_id={self.flow_id}")
        prepared = await self._prepare_a2a_params(params)

        # A2A Section 3.4.3: follow-up при активном operator takeover
        if prepared.is_takeover_user_reply:
            async for event in self._handle_takeover_user_reply(prepared):
                yield event
            return

        logger.info(f"[on_message_stream] Prepared task_id={prepared.task_id}, subscribing to Redis...")
        container = get_container()

        subscriber = EventSubscriber(container.redis_client)
        event_queue: asyncio.Queue = asyncio.Queue()
        ready_event = asyncio.Event()

        async def collect_events():
            async for event in subscriber.subscribe(prepared.task_id, ready_event=ready_event):
                await event_queue.put(event)
            await event_queue.put(None)

        collect_task = asyncio.create_task(collect_events())

        logger.info(f"[on_message_stream] Waiting for Redis subscription to be ready...")
        await ready_event.wait()
        logger.info(f"[on_message_stream] Redis subscription ready, creating task...")

        await self.create_task(prepared)

        while True:
            event = await event_queue.get()
            if event is None:
                break
            yield event

        await collect_task

    async def on_get_task(self, params: TaskQueryParams, context: Any = None) -> Optional[Task]:
        """Получение задачи по ID."""
        task = await self._get_task_from_state(params.id)

        if task and params.history_length and task.history:
            task.history = task.history[-params.history_length :]

        return task

    async def on_cancel_task(self, params: TaskIdParams, context: Any = None) -> Optional[Task]:
        """Отмена задачи. Ставит Redis-ключ для остановки воркера на следующем такте."""
        logger.info(f"Cancel task: {params.id}")

        container = get_container()
        await container.redis_client.set(f"cancel:{params.id}", "1", ttl=CANCEL_KEY_TTL)

        task = await self._cancel_task_in_state(params.id)

        if task:
            await send_task_update.kiq(
                task_id=params.id,
                context_id=params.id,
                state="canceled",
                message="Task cancelled",
                is_final=True,
            )

        return task

    async def on_resubscribe_to_task(
        self, params: TaskIdParams, context: Any = None
    ) -> AsyncGenerator[Union[Message, Task, TaskStatusUpdateEvent, TaskArtifactUpdateEvent], None]:
        """Переподписка на события задачи."""
        task = await self.on_get_task(TaskQueryParams(id=params.id))
        if task:
            yield task

    async def on_set_task_push_notification_config(
        self, params: TaskPushNotificationConfig, context: Any = None
    ) -> TaskPushNotificationConfig:
        """Установка конфигурации push notification."""
        data = await set_config(params)
        logger.info(f"Set push notification config for task: {params.task_id}")
        return dict_to_config(data)

    async def on_get_task_push_notification_config(
        self, params: GetTaskPushNotificationConfigParams, context: Any = None
    ) -> Optional[TaskPushNotificationConfig]:
        """Получение конфигурации push notification."""
        data = await get_config(params)
        logger.info(f"Get push notification config for task: {params.id}")
        return dict_to_config(data) if data else None

    async def on_list_task_push_notification_config(
        self, params: ListTaskPushNotificationConfigParams, context: Any = None
    ) -> List[TaskPushNotificationConfig]:
        """Список конфигураций push notification."""
        configs = await list_configs(params)
        logger.info(f"List push notification configs for task: {params.id}, found: {len(configs)}")
        return [dict_to_config(data) for data in configs]

    async def on_delete_task_push_notification_config(
        self, params: DeleteTaskPushNotificationConfigParams, context: Any = None
    ) -> None:
        """Удаление конфигурации push notification."""
        await delete_config(params)
        logger.info(
            f"Deleted push notification config: {params.push_notification_config_id} for task: {params.id}"
        )

    async def on_get_authenticated_extended_card(self, params: Any, context: Any = None) -> Any:
        """Получение расширенной карточки агента."""
        return None
