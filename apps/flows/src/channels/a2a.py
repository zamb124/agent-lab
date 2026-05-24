"""
A2AChannel - реализация A2A протокола.

Полная поддержка A2A спецификации через a2a-sdk.
Поддержка evaluation через metadata.evaluation.test_case_id.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import override

from a2a.types import (
    AgentCard,
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
from pydantic import Field

from apps.flows.config import FLOWS_PUBLIC_API_PREFIX
from apps.flows.src.channels.base import BaseChannel
from apps.flows.src.channels.types import ChannelRequestContext, PreparedTaskParams
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.files import (
    extract_incoming_a2a_files,
    format_a2a_files_content,
    transcribe_incoming_audio_files,
)
from apps.flows.src.services.push_notifications import dict_to_config
from apps.flows.src.state.cancellation import CANCEL_KEY_TTL
from apps.flows.src.streaming import Emitter
from apps.flows.src.streaming.base import StreamEvent
from apps.flows.src.streaming.subscriber import EventSubscriber
from apps.flows.src.utils import extract_json_from_response
from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.tasks.task_names import TASK_SEND_TASK_UPDATE
from core.config.testing import is_testing
from core.context import set_current_channel
from core.files.file_ref import FileRef, file_id_from_download_url
from core.logging import get_logger
from core.models import StrictBaseModel
from core.state import ExecutionState
from core.tasks.kicker import kiq_task_name_with_context
from core.tasks.push_notifications import (
    delete_push_config,
    get_push_config,
    list_push_configs,
    set_push_config,
)
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)


class A2AEvaluationMetadata(StrictBaseModel):
    """Строгий контракт metadata.evaluation публичного A2A message/send."""

    test_case_id: str = Field(min_length=1)


def _text_part(text: str) -> Part:
    return Part(root=TextPart(text=text))


def _data_part(data: JsonObject) -> Part:
    return Part(root=DataPart(data=data))


def _part_text(part: Part) -> str | None:
    root = part.root
    return root.text if isinstance(root, TextPart) else None


def _message_metadata(params: MessageSendParams) -> JsonObject | None:
    if params.metadata is None:
        return None
    return require_json_object(params.metadata, "a2a.message.metadata")


def _branch_id_from_message_metadata(metadata: JsonObject | None) -> str:
    if not metadata:
        return "default"
    branch = metadata.get("branch")
    if branch is None:
        return "default"
    if not isinstance(branch, str) or not branch.strip():
        raise ValueError("a2a.message.metadata.branch must be a non-empty string")
    return branch.strip()


def _get_evaluation_metadata(metadata: JsonObject | None) -> A2AEvaluationMetadata | None:
    """Извлекает параметры evaluation из metadata."""
    if not metadata:
        return None
    evaluation = metadata.get("evaluation")
    if evaluation is None:
        return None
    return A2AEvaluationMetadata.model_validate(evaluation)


def _is_async_message_send(metadata: JsonObject | None) -> bool:
    """Совместимый async-режим для A2A message/send без ожидания финального результата."""
    if not metadata:
        return False
    for key in ("execution_mode", "mode"):
        raw = metadata.get(key)
        if raw is None:
            continue
        if not isinstance(raw, str):
            raise ValueError(f"a2a.message.metadata.{key} must be a string")
        return raw.strip().lower() in {"async", "background"}
    return False


async def _build_task_from_events(
    events: list[StreamEvent],
    task_id: str,
    context_id: str,
    input_message: Message,
    flow_id: str,
    container: FlowRuntimeContainer | None = None,
) -> Task:
    """
    Строит Task из накопленных событий.

    Извлекает artifacts, status, response из событий и формирует Task по A2A SDK.
    Разделяет артефакты по именам (response vs reasoning).
    Загружает существующую историю из state для multi-turn сценариев.
    """
    artifacts_dict: dict[str, Artifact] = {}
    final_status: TaskStatus | None = None
    response_parts: list[str] = []
    reasoning_parts: list[str] = []

    for event in events:
        if isinstance(event, TaskArtifactUpdateEvent):
            if event.artifact:
                artifact_name = event.artifact.name or "response"
                for part in event.artifact.parts:
                    text = _part_text(part)
                    if text is not None:
                        if artifact_name == "reasoning":
                            if event.append:
                                reasoning_parts.append(text)
                            else:
                                reasoning_parts = [text]
                        elif artifact_name == "response":
                            if event.append:
                                response_parts.append(text)
                            else:
                                response_parts = [text]
        else:
            if event.final:
                final_status = event.status

    response_text = "".join(response_parts)
    if not response_text and final_status and final_status.message and final_status.message.parts:
        status_message_parts: list[str] = []
        for part in final_status.message.parts:
            text = _part_text(part)
            if text is not None:
                status_message_parts.append(text)
        response_text = "".join(status_message_parts)

    if reasoning_parts:
        reasoning_text = "".join(reasoning_parts)
        artifacts_dict["reasoning"] = Artifact(
            artifact_id=str(uuid.uuid4()),
            name="reasoning",
            parts=[_text_part(reasoning_text)],
        )

    # Проверяем есть ли JSON в ответе
    json_data = extract_json_from_response(response_text)

    # Создаем response artifact:
    # 1. Для JSON данных - как DataPart (всегда создаем если найден JSON)
    # 2. Для текстовых ответов - только если есть reasoning (чтобы разделить reasoning и response)
    if json_data is not None:
        artifacts_dict["response"] = Artifact(
            artifact_id=str(uuid.uuid4()),
            name="response",
            parts=[_data_part({"res": json.dumps(json_data, ensure_ascii=False)})],
        )
    elif response_text and reasoning_parts:
        artifacts_dict["response"] = Artifact(
            artifact_id=str(uuid.uuid4()),
            name="response",
            parts=[_text_part(response_text)],
        )

    artifacts = list(artifacts_dict.values())

    if final_status is None:
        final_status = TaskStatus(
            state=TaskState.completed,
            message=new_agent_text_message(response_text) if response_text else None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # Загружаем существующую историю из state для multi-turn сценариев
    session_id = f"{flow_id}:{context_id}"
    existing_history: list[Message] = []
    if container is not None:
        state = await container.state_manager.get_state(session_id)
        existing_history = state.messages if state else []

    # Устанавливаем task_id в input_message для истории
    history_message = input_message.model_copy(update={"task_id": task_id})

    # Для existing_history устанавливаем task_id если его нет
    for msg in existing_history:
        if hasattr(msg, "task_id") and not msg.task_id:
            msg.task_id = task_id

    history: list[Message] = [*existing_history, history_message]

    if response_text and final_status.state == TaskState.completed:
        agent_message = new_agent_text_message(response_text)
        agent_message.task_id = task_id
        history.append(agent_message)
    elif final_status.state == TaskState.input_required and final_status.message:
        agent_message = final_status.message
        if not agent_message.task_id:
            agent_message = agent_message.model_copy(update={"task_id": task_id})
        history.append(agent_message)

    # Когда есть artifacts (response/reasoning), не дублируем ответ в status.message.
    # Сохраняем message для input_required (вопрос), failed/canceled (текст ошибки для клиента).
    if (
        artifacts
        and final_status.message
        and final_status.state
        not in (
            TaskState.input_required,
            TaskState.failed,
            TaskState.canceled,
        )
    ):
        timestamp = final_status.timestamp or datetime.now(timezone.utc).isoformat()
        final_status = TaskStatus(
            state=final_status.state,
            timestamp=timestamp,
            message=None,
        )

    return Task(
        id=task_id,
        context_id=context_id,
        status=final_status,
        artifacts=artifacts if artifacts else None,
        history=history,
    )


class A2AChannel(BaseChannel):
    """
    A2A канал коммуникации.

    Полная реализация A2A протокола через a2a-sdk.
    """

    name: str = "a2a"

    @override
    async def send_to_user(
        self,
        content: str,
        buttons: list[str] | None = None,
        attachments: list[JsonObject] | None = None,
    ) -> None:
        """
        Отправляет сообщение пользователю через A2A.

        В A2A это делается через emit событий в Redis Pub/Sub.
        """
        _ = buttons, attachments
        if not self.context:
            logger.warning("Cannot send_to_user: no context available")
            return

        task_id = self.context.metadata.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("A2AChannel.send_to_user requires context.metadata.task_id")
        context_id = self.context.metadata.get("context_id")
        if not isinstance(context_id, str) or not context_id:
            raise ValueError("A2AChannel.send_to_user requires context.metadata.context_id")
        session_id = self._generate_session_id(context_id)

        exec_state = ExecutionState(
            task_id=task_id,
            context_id=context_id,
            session_id=session_id,
            user_id=self.context.user.user_id,
            user_groups=self._get_user_groups_from_context(self.context),
        )
        emitter = Emitter(self.container.redis_client, exec_state)
        await emitter.emit_text(content, append=False, last_chunk=True)

    async def _handle_takeover_user_reply(
        self,
        prepared: PreparedTaskParams,
    ) -> AsyncGenerator[TaskStatusUpdateEvent, None]:
        """A2A Section 3.4.3: follow-up при input-required с operator takeover.

        Маршрутизирует текст пользователя в dialog_log без запуска flow.
        Возвращает status-update input-required (задача остаётся в ожидании оператора).
        """
        svc = self.container.operator_handoff_service
        if self.context is None or self.context.active_company is None:
            raise ValueError("A2A takeover reply requires active_company in context")

        file_ids: list[str] = []
        if prepared.files_data:
            for file_ref in prepared.files_data:
                if file_ref.file_id is not None:
                    file_ids.append(file_ref.file_id)
                    continue
                if file_ref.url is not None and file_ref.url.startswith(("http://", "https://")):
                    continue
                if file_ref.url is not None:
                    raise ValueError(
                        "Вложение A2A без file_id: ожидается персист через API (S3), "
                        + "локальные url в state.files не поддерживаются."
                    )

        operator_task_id = prepared.takeover_operator_task_id
        if operator_task_id is None:
            raise ValueError("takeover_operator_task_id is required for takeover user reply")

        await svc.receive_user_reply(
            company_id=self.context.active_company.company_id,
            task_id=operator_task_id,
            text=prepared.content,
            user_id=prepared.user_id,
            file_ids=file_ids if file_ids else None,
        )
        logger.info(
            "[on_message_stream] takeover user-reply routed to dialog_log, "
            + "task_id=%s, operator_task=%s",
            prepared.task_id,
            operator_task_id,
        )
        yield TaskStatusUpdateEvent(
            task_id=prepared.task_id,
            context_id=prepared.context_id,
            status=TaskStatus(
                state=TaskState.input_required,
                message=new_agent_text_message(prepared.content),
            ),
            final=True,
        )

    async def _persist_incoming_a2a_files(self, message: Message) -> tuple[list[FileRef], str]:
        """Байты FileWithBytes -> S3 + FileRecord; FileWithUri -> canonical url в state."""
        incoming = extract_incoming_a2a_files(message)
        if not incoming:
            return [], ""

        if not self.context or not self.context.active_company:
            raise ValueError(
                "Загрузка вложений A2A требует active_company в контексте запроса"
            )

        company_id = self.context.active_company.company_id
        user_id = self.context.user.user_id if self.context.user else None
        prefix = f"{FLOWS_PUBLIC_API_PREFIX}/files/download"
        files_data: list[FileRef] = []

        for inc in incoming:
            if inc.data is not None:
                if not inc.content_type or not inc.content_type.strip():
                    raise ValueError("FileWithBytes.content_type обязателен для state.files")
                item = await self.container.file_processor.persist_uploaded_file_as_file_ref(
                    data=inc.data,
                    original_name=inc.original_name,
                    content_type=inc.content_type.strip(),
                    uploaded_by=user_id,
                    company_id=company_id,
                    public=False,
                    download_url_prefix=prefix,
                )
                files_data.append(item)
            else:
                if not inc.uri:
                    raise ValueError("FileWithUri без uri")
                if not inc.content_type or not inc.content_type.strip():
                    raise ValueError("FileWithUri.content_type обязателен для state.files")
                linked_file_id = file_id_from_download_url(inc.uri)
                if linked_file_id:
                    record = await self.container.file_processor.get_file_record(linked_file_id)
                    if record is None:
                        raise ValueError(f"FileWithUri с неизвестным file_id: {linked_file_id}")
                    if record.company_id != company_id:
                        raise ValueError("FileWithUri file_id не принадлежит активной компании")
                    item = FileRef(
                        file_id=record.file_id,
                        original_name=record.original_name,
                        url=record.download_url if record.download_url is not None else inc.uri,
                        content_type=record.content_type,
                        file_size=record.file_size,
                        checksum=record.checksum,
                        is_public=record.is_public,
                    )
                else:
                    item = FileRef(
                        original_name=inc.original_name,
                        url=inc.uri,
                        content_type=inc.content_type.strip(),
                        file_size=inc.file_size,
                    )
                files_data.append(item)

        return files_data, format_a2a_files_content(files_data)

    async def _transcribe_incoming_audio(
        self, files_data: list[FileRef]
    ) -> str:
        """
        Авто-STT для входящих audio-вложений (`audio/*` по mime/расширению).

        Единая точка для A2A SDK/CLI, embed-chat и нашего чата: все они идут
        через `_persist_incoming_a2a_files`, поэтому транскрипция делается
        один раз тут. Провайдер STT и модель резолвит `voice_resolver`
        (override → company → deployment-default).
        """
        if not self.context or not self.context.active_company:
            raise ValueError(
                "Авто-STT входящих audio-вложений требует active_company в контексте запроса"
            )
        return await transcribe_incoming_audio_files(
            container=self.container,
            files_data=files_data,
            company_id=self.context.active_company.company_id,
        )

    async def _prepare_a2a_params(
        self, params: MessageSendParams, metadata: JsonObject | None = None
    ) -> PreparedTaskParams:
        """Подготовка параметров специфичных для A2A."""
        message = params.message
        content = get_message_text(message)

        files_data, files_content_suffix = await self._persist_incoming_a2a_files(message)
        if files_data:
            audio_transcript_suffix = await self._transcribe_incoming_audio(files_data)
            if audio_transcript_suffix:
                content += audio_transcript_suffix
        if files_content_suffix:
            content += files_content_suffix

        prepared = await self._prepare_task_params(
            content=content,
            context_id=message.context_id,
            task_id=message.task_id,
            message=message,
            metadata=metadata if metadata is not None else _message_metadata(params),
            files_data=files_data,
        )

        return prepared

    @override
    async def on_message_send(
        self, params: MessageSendParams, context: ChannelRequestContext = None
    ) -> Task | Message:
        """
        По умолчанию совместимый синхронный режим: кикает task и собирает события через collect().
        Если metadata.execution_mode == "async", возвращает submitted Task сразу; результат
        забирается через tasks/get по task_id или context_id.

        Поддерживает evaluation через metadata.evaluation:
        - test_case_id: ID тест-кейса для запуска

        ВАЖНО: подписка на канал ПЕРЕД киком задачи, иначе race condition -
        события могут быть опубликованы до подписки и потеряны.

        Args:
            params: параметры сообщения
            context: контекст с user_groups для проверки permissions
        """
        set_current_channel(self)

        metadata = _message_metadata(params)
        branch_for_perm = _branch_id_from_message_metadata(metadata)
        await self.check_permissions(self._get_user_groups_from_context(context), branch_for_perm)

        # Проверяем evaluation mode
        eval_metadata = _get_evaluation_metadata(metadata)
        if eval_metadata is not None:
            eval_task_id = params.message.task_id or str(uuid.uuid4())
            # Собираем все события и формируем Task
            events = [
                event
                async for event in self._run_evaluation(
                    params, metadata, eval_metadata, task_id=eval_task_id
                )
            ]
            return await _build_task_from_events(
                events=events,
                task_id=eval_task_id,
                context_id=params.message.context_id or str(uuid.uuid4()),
                input_message=params.message,
                flow_id=self.flow_id,
                container=self.container,
            )

        # Обычный режим
        prepared = await self._prepare_a2a_params(params, metadata)

        # A2A Section 3.4.3: follow-up при активном operator takeover
        if prepared.is_takeover_user_reply:
            events: list[StreamEvent] = [
                event async for event in self._handle_takeover_user_reply(prepared)
            ]
            if prepared.message is None:
                raise ValueError("A2A prepared params must include original message")
            return await _build_task_from_events(
                events=events,
                task_id=prepared.task_id,
                context_id=prepared.context_id,
                input_message=prepared.message,
                flow_id=self.flow_id,
                container=self.container,
            )

        if _is_async_message_send(metadata):
            await self.create_task(prepared)
            return Task(
                id=prepared.task_id,
                context_id=prepared.context_id,
                status=TaskStatus(
                    state=TaskState.submitted,
                    message=new_agent_text_message("Task submitted"),
                ),
                history=[prepared.message] if prepared.message is not None else None,
            )

        # Таймаут короче для тестов
        timeout = 30.0 if is_testing() else 300.0

        subscriber = EventSubscriber(self.container.redis_client)
        ready_event = asyncio.Event()

        async def collect_with_subscription():
            return await subscriber.collect(prepared.task_id, timeout=timeout, ready_event=ready_event)

        collect_task = asyncio.create_task(collect_with_subscription())

        _ = await ready_event.wait()

        logger.debug(f"[A2A] Subscribed to stream:{prepared.task_id}, kicking task")
        await self.create_task(prepared)

        events = await collect_task

        logger.debug(f"[A2A] Collected {len(events)} events for task {prepared.task_id}")
        if prepared.message is None:
            raise ValueError("A2A prepared params must include original message")

        return await _build_task_from_events(
            events=events,
            task_id=prepared.task_id,
            context_id=prepared.context_id,
            input_message=prepared.message,
            flow_id=self.flow_id,
            container=self.container,
        )

    async def _run_evaluation(
        self,
        params: MessageSendParams,
        metadata: JsonObject | None,
        eval_metadata: A2AEvaluationMetadata,
        task_id: str,
    ) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        """
        Запускает evaluation тест через EvaluationService и yield'ит A2A события.

        A2A канал только конвертирует события сервиса в A2A формат.
        Вся логика тестирования в EvaluationService.
        """
        test_case_id = eval_metadata.test_case_id

        branch_id = _branch_id_from_message_metadata(metadata)
        context_id = params.message.context_id or str(uuid.uuid4())

        service = self.container.evaluation_service

        try:
            async for event in service.run_test_stream(
                self.flow_id, branch_id, test_case_id, task_id=task_id
            ):
                if event["type"] == "error":
                    raise ValueError(event["message"])

                elif event["type"] == "start":
                    yield TaskArtifactUpdateEvent(
                        task_id=task_id,
                        context_id=context_id,
                        artifact=Artifact(
                            artifact_id=str(uuid.uuid4()),
                            name="response",
                            parts=[_text_part(f"🧪 Запуск теста: {test_case_id}\n\n")],
                        ),
                        append=False,
                        last_chunk=False,
                    )

                elif event["type"] == "user":
                    text = f"👤 **USER**: {event['content']}\n"
                    yield TaskArtifactUpdateEvent(
                        task_id=task_id,
                        context_id=context_id,
                        artifact=Artifact(
                            artifact_id=str(uuid.uuid4()),
                            name="response",
                            parts=[_text_part(text)],
                        ),
                        append=True,
                        last_chunk=False,
                    )

                elif event["type"] == "assistant":
                    text = f"🤖 **ASSISTANT**: {event['content']}\n\n"
                    yield TaskArtifactUpdateEvent(
                        task_id=task_id,
                        context_id=context_id,
                        artifact=Artifact(
                            artifact_id=str(uuid.uuid4()),
                            name="response",
                            parts=[_text_part(text)],
                        ),
                        append=True,
                        last_chunk=False,
                    )

                elif event["type"] == "result":
                    status_icon = "" if event["status"] == "passed" else "❌"
                    result_text = f"\n---\n{status_icon} **Результат**: {event['status'].upper()}"
                    result_text += f"\n⏱Время: {event['duration_ms']}ms"
                    turns_count = event["turns_count"] if "turns_count" in event else 0
                    if turns_count > 0:
                        result_text += f"\n💬 Ходов: {turns_count}"
                    error = event["error"] if "error" in event else None
                    if error:
                        result_text += f"\n⚠️ Ошибка: {error}"

                    # task_id для трейсинга
                    eval_task_id = event.get("task_id")
                    if eval_task_id:
                        result_text += f"\nTask ID: {eval_task_id}"

                    yield TaskArtifactUpdateEvent(
                        task_id=task_id,
                        context_id=context_id,
                        artifact=Artifact(
                            artifact_id=str(uuid.uuid4()),
                            name="response",
                            parts=[_text_part(result_text)],
                        ),
                        append=True,
                        last_chunk=True,
                    )

                    # Для evaluation тестов всегда completed - passed/failed это результат теста, а не ошибка
                    yield TaskStatusUpdateEvent(
                        task_id=task_id,
                        context_id=context_id,
                        status=TaskStatus(state=TaskState.completed),
                        final=True,
                    )

        except Exception as e:
            logger.exception(f"Error running evaluation test {test_case_id}")

            yield TaskArtifactUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                artifact=Artifact(
                    artifact_id=str(uuid.uuid4()),
                    name="response",
                    parts=[_text_part(f"❌ Ошибка теста: {str(e)}")],
                ),
                append=True,
                last_chunk=True,
            )
            yield TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.failed),
                final=True,
            )

    @override
    async def on_message_stream(
        self, params: MessageSendParams, context: ChannelRequestContext = None
    ) -> AsyncGenerator[Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
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

        metadata = _message_metadata(params)
        branch_for_perm = _branch_id_from_message_metadata(metadata)
        await self.check_permissions(self._get_user_groups_from_context(context), branch_for_perm)

        # Проверяем evaluation mode
        eval_metadata = _get_evaluation_metadata(metadata)
        if eval_metadata is not None:
            eval_task_id = params.message.task_id or str(uuid.uuid4())
            async for event in self._run_evaluation(
                params, metadata, eval_metadata, task_id=eval_task_id
            ):
                yield event
            return

        # Обычный режим
        prepared = await self._prepare_a2a_params(params, metadata)

        # A2A Section 3.4.3: follow-up при активном operator takeover
        if prepared.is_takeover_user_reply:
            async for event in self._handle_takeover_user_reply(prepared):
                yield event
            return

        logger.info(f"[on_message_stream] Prepared task_id={prepared.task_id}, subscribing to Redis...")
        subscriber = EventSubscriber(self.container.redis_client)
        event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
        ready_event = asyncio.Event()

        async def collect_events():
            async for event in subscriber.subscribe(prepared.task_id, ready_event=ready_event):
                await event_queue.put(event)
            await event_queue.put(None)

        collect_task = asyncio.create_task(collect_events())

        logger.info("[on_message_stream] Waiting for Redis subscription to be ready...")
        _ = await ready_event.wait()
        logger.info("[on_message_stream] Redis subscription ready, creating task...")

        await self.create_task(prepared)

        while True:
            event = await event_queue.get()
            if event is None:
                break
            yield event

        await collect_task

    @override
    async def on_get_task(
        self, params: TaskQueryParams, context: ChannelRequestContext = None
    ) -> Task | None:
        """Получение задачи по ID."""
        _ = context
        task = await self._get_task_from_state(params.id)

        if task and params.history_length and task.history:
            task.history = task.history[-params.history_length :]

        return task

    @override
    async def on_cancel_task(
        self, params: TaskIdParams, context: ChannelRequestContext = None
    ) -> Task | None:
        """Отмена задачи. Ставит Redis-ключ для остановки воркера на следующем такте."""
        _ = context
        logger.info(f"Cancel task: {params.id}")

        _ = await self.container.redis_client.set(f"cancel:{params.id}", "1", ttl=CANCEL_KEY_TTL)

        task = await self._cancel_task_in_state(params.id)

        if task:
            _ = await kiq_task_name_with_context(
                TASK_SEND_TASK_UPDATE,
                idle_broker,
                task.id,
                task.context_id,
                "canceled",
                "Task cancelled",
                True,
                background_kind="a2a_task",
            )

        return task

    @override
    async def on_resubscribe_to_task(
        self, params: TaskIdParams, context: ChannelRequestContext = None
    ) -> AsyncGenerator[Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        """Переподписка на события задачи."""
        _ = context
        task = await self.on_get_task(TaskQueryParams(id=params.id))
        if task:
            yield task

    @override
    async def on_set_task_push_notification_config(
        self, params: TaskPushNotificationConfig, context: ChannelRequestContext = None
    ) -> TaskPushNotificationConfig:
        """Установка конфигурации push notification."""
        _ = context
        data = await set_push_config(params)
        logger.info(f"Set push notification config for task: {params.task_id}")
        return dict_to_config(data)

    @override
    async def on_get_task_push_notification_config(
        self,
        params: GetTaskPushNotificationConfigParams,
        context: ChannelRequestContext = None,
    ) -> TaskPushNotificationConfig | None:
        """Получение конфигурации push notification."""
        _ = context
        data = await get_push_config(params)
        logger.info(f"Get push notification config for task: {params.id}")
        return dict_to_config(data) if data else None

    @override
    async def on_list_task_push_notification_config(
        self,
        params: ListTaskPushNotificationConfigParams,
        context: ChannelRequestContext = None,
    ) -> list[TaskPushNotificationConfig]:
        """Список конфигураций push notification."""
        _ = context
        configs = await list_push_configs(params)
        logger.info(f"List push notification configs for task: {params.id}, found: {len(configs)}")
        return [dict_to_config(data) for data in configs]

    @override
    async def on_delete_task_push_notification_config(
        self,
        params: DeleteTaskPushNotificationConfigParams,
        context: ChannelRequestContext = None,
    ) -> None:
        """Удаление конфигурации push notification."""
        _ = context
        await delete_push_config(params)
        logger.info(
            f"Deleted push notification config: {params.push_notification_config_id} for task: {params.id}"
        )

    @override
    async def on_get_authenticated_extended_card(
        self,
        params: JsonObject,
        context: ChannelRequestContext = None,
    ) -> AgentCard | None:
        """Получение расширенной карточки агента."""
        _ = params, context
        return None
