"""
Emitter - публикация A2A событий в Redis Pub/Sub.
"""

from typing import Protocol, Self, override

from a2a.types import Message
from google.protobuf.json_format import MessageToDict

from apps.flows.src.a2a.ensure_submitted_task import ensure_submitted_a2a_task
from apps.flows.src.a2a.task_projection_service import A2ATaskProjectionService
from apps.flows.src.db.a2a_task_repository import A2ATaskRepository
from apps.flows.src.observability.flow_timing import maybe_record_flow_first_content_chunk
from core.a2a import struct_from_mapping
from core.context import require_context
from core.flow_ui.protocol import RESPONSE_ARTIFACT_NAME
from core.logging import get_logger
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

from .base import BaseEmitter, StreamEvent


class A2AEmitterContainer(Protocol):
    @property
    def a2a_task_projection_service(self) -> A2ATaskProjectionService: ...

    @property
    def a2a_task_repository(self) -> A2ATaskRepository: ...

logger = get_logger(__name__)


class Emitter(BaseEmitter):
    """
    Публикация событий в Redis Pub/Sub.

    Все события автоматически получают:
    - task_id
    - context_id
    - trace_id (из OpenTelemetry контекста)
    - span_id (из OpenTelemetry контекста)

    Durable append требует Task projection: для новых путей используй
    ``create_ensured``. ``from_container`` — только когда Task уже ensured.

    Примеры:
        >>> emitter = await Emitter.create_ensured(container, state)
        >>> await emitter.emit_text("Привет")
        >>> await emitter.emit_complete("Готово")
    """

    projection_service: A2ATaskProjectionService
    company_id: str
    _first_content_chunk_recorded: bool

    def __init__(
        self,
        projection_service: A2ATaskProjectionService,
        state: ExecutionState,
        *,
        company_id: str,
    ) -> None:
        """
        Аргументы:
            projection_service: durable projection and Redis publication service
            state: ExecutionState с task_id, context_id
        """
        if company_id.strip() == "":
            raise ValueError("Emitter company_id is required")
        super().__init__(state)
        self.projection_service = projection_service
        self.company_id = company_id
        self._first_content_chunk_recorded = False

    @classmethod
    def from_container(
        cls,
        container: A2AEmitterContainer,
        state: ExecutionState,
    ) -> Self:
        context = require_context()
        if context.active_company is None:
            raise ValueError("Durable A2A emitter requires active_company")
        return cls(
            container.a2a_task_projection_service,
            state,
            company_id=context.active_company.company_id,
        )

    @classmethod
    async def create_ensured(
        cls,
        container: A2AEmitterContainer,
        state: ExecutionState,
        *,
        input_message: Message | None = None,
        content: str | None = None,
    ) -> Self:
        """Ensure SUBMITTED Task projection, then build a durable Emitter."""
        context = require_context()
        if context.active_company is None:
            raise ValueError("Durable A2A emitter requires active_company")
        await ensure_submitted_a2a_task(
            repository=container.a2a_task_repository,
            company_id=context.active_company.company_id,
            state=state,
            input_message=input_message,
            content=content,
        )
        return cls.from_container(container, state)

    @override
    async def emit_text(
        self,
        text: str,
        append: bool = True,
        last_chunk: bool = False,
        *,
        artifact_name: str = RESPONSE_ARTIFACT_NAME,
    ) -> None:
        if (
            artifact_name == "response"
            and text != ""
            and not self._first_content_chunk_recorded
        ):
            self._first_content_chunk_recorded = True
            flow_id = self.state.session_flow_id
            await maybe_record_flow_first_content_chunk(
                self.projection_service.redis_client,
                task_id=self.state.task_id,
                flow_id=flow_id,
                text=text,
            )
        await super().emit_text(
            text,
            append=append,
            last_chunk=last_chunk,
            artifact_name=artifact_name,
        )

    @override
    async def _publish(self, event: StreamEvent) -> None:
        """
        Публикует событие в Redis как A2A 1.0 StreamResponse (MessageToDict).

        Аргументы:
            event: A2A событие
        """
        if self._span_context:
            meta: JsonObject = {
                "trace_id": self._span_context.get("trace_id"),
                "span_id": self._span_context.get("span_id"),
            }
            if event.HasField("metadata"):
                existing = require_json_object(
                    MessageToDict(event.metadata),
                    "StreamEvent.metadata",
                )
                meta = {**existing, **meta}
            event.metadata.CopyFrom(struct_from_mapping(meta))

        _ = await self.projection_service.publish(
            company_id=self.company_id,
            event=event,
        )

__all__ = ["Emitter"]
