"""
Базовые абстрактные классы для стриминга событий.
"""

import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional, Union

from a2a.types import (
    Artifact,
    DataPart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

from core.state import ExecutionState
from core.state.interrupt import InterruptKind

if TYPE_CHECKING:
    from core.state import InterruptData

StreamEvent = Union[TaskStatusUpdateEvent, TaskArtifactUpdateEvent]


class BaseEmitter(ABC):
    """
    Базовый класс для публикации событий.

    Реализации:
    - RedisEmitter: публикация в Redis Pub/Sub
    - InMemoryEmitter: хранение в памяти (для внешних агентов)
    """

    def __init__(self, state: ExecutionState):
        self.state = state
        self._span_context = None

    def _create_message(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """Создаёт A2A Message объект."""
        return Message(
            messageId=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=text))],
            metadata=metadata,
        )

    async def emit_text(
        self,
        text: str,
        append: bool = True,
        last_chunk: bool = False,
        *,
        artifact_name: str = "response",
    ) -> None:
        """Публикует текстовый чанк (LLM: response; оператор: operator_reply)."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=artifact_name,
            parts=[TextPart(text=text)],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
            append=append,
            last_chunk=last_chunk,
        )

        await self._publish(event)

    async def emit_reasoning(self, text: str) -> None:
        """Публикует чанк reasoning (тот же контракт, что emit_text с именем артефакта reasoning)."""
        await self.emit_text(text, append=True, last_chunk=False, artifact_name="reasoning")

    async def emit_tool_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_call_id: str,
        react_role: str = "standard",
    ) -> None:
        """Публикует событие вызова инструмента."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=f"tool_call_{tool_call_id}",
            parts=[DataPart(data={
                "tool": tool_name,
                "args": tool_args,
                "tool_call_id": tool_call_id,
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_tool_result(
        self,
        tool_name: str,
        result: Any,
        tool_call_id: str,
    ) -> None:
        """Публикует результат выполнения инструмента."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=f"tool_result_{tool_call_id}",
            parts=[DataPart(data={
                "tool": tool_name,
                "result": result,
                "tool_call_id": tool_call_id,
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_complete(
        self,
        response: str,
        message_id: Optional[str] = None,
        has_artifact: bool = False,
    ) -> None:
        """Публикует событие завершения выполнения."""
        event = TaskStatusUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            status=TaskStatus(
                state=TaskState.completed,
                message=self._create_message(response),
            ),
            final=True,
        )

        await self._publish(event)

    async def emit_interrupt(
        self,
        interrupt: "InterruptData",
        message_id: Optional[str] = None,
    ) -> None:
        """Публикует input_required с полным объектом interrupt в metadata."""
        dump = interrupt.model_dump(mode="json")
        meta: Dict[str, Any] = {"platform_interrupt": dump}
        is_operator = interrupt.body.kind == InterruptKind.OPERATOR_TASK
        is_oauth = interrupt.body.kind == InterruptKind.OAUTH_REQUIRED
        keep_stream_open = is_operator or is_oauth
        if is_operator:
            meta["platform_handoff_continue"] = True
        if is_oauth:
            meta["platform_oauth_continue"] = True
        event = TaskStatusUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            status=TaskStatus(
                state=TaskState.input_required,
                message=self._create_message(interrupt.question, metadata=meta),
            ),
            final=not keep_stream_open,
            metadata=meta,
        )

        await self._publish(event)

    async def emit_cancelled(self) -> None:
        """Публикует событие отмены выполнения."""
        event = TaskStatusUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            status=TaskStatus(
                state=TaskState.canceled,
                message=self._create_message("Task cancelled"),
            ),
            final=True,
        )
        await self._publish(event)

    async def emit_error(
        self,
        error: str,
        message_id: Optional[str] = None,
    ) -> None:
        """Публикует событие ошибки."""
        event = TaskStatusUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            status=TaskStatus(
                state=TaskState.failed,
                message=self._create_message(error),
            ),
            final=True,
        )

        await self._publish(event)

    async def emit(self, event: Any) -> None:
        """Публикует произвольное событие (StreamEvent от runner)."""
        await self._publish(event)

    async def emit_node_start(
        self,
        node_id: str,
        node_type: str,
    ) -> None:
        """Публикует событие начала выполнения ноды."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=f"node_start_{node_id}",
            parts=[DataPart(data={
                "event": "node_start",
                "node_id": node_id,
                "node_type": node_type,
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_node_complete(
        self,
        node_id: str,
        result_preview: str = "",
    ) -> None:
        """Публикует событие завершения ноды."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=f"node_complete_{node_id}",
            parts=[DataPart(data={
                "event": "node_complete",
                "node_id": node_id,
                "result_preview": result_preview[:200],
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_node_error(
        self,
        node_id: str,
        error: str,
    ) -> None:
        """Публикует событие ошибки в ноде."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=f"node_error_{node_id}",
            parts=[DataPart(data={
                "event": "node_error",
                "node_id": node_id,
                "error": error[:500],
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_edge_executed(
        self,
        edge_index: int,
        from_node: str,
        to_node: str,
    ) -> None:
        """Публикует факт прохождения ребра (для подсветки графа в UI)."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=f"edge_executed_{edge_index}_{from_node}_{to_node}",
            parts=[DataPart(data={
                "event": "edge_executed",
                "edge_index": edge_index,
                "from_node": from_node,
                "to_node": to_node,
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_edge_error(
        self,
        edge_index: int,
        from_node: str,
        to_node: str,
        error: str,
    ) -> None:
        """Публикует ошибку вычисления условия ребра (подсветка в UI)."""
        err = error if len(error) <= 500 else error[:500]
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=f"edge_error_{edge_index}_{from_node}_{to_node}",
            parts=[DataPart(data={
                "event": "edge_error",
                "edge_index": edge_index,
                "from_node": from_node,
                "to_node": to_node,
                "error": err,
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_file_artifact(
        self,
        file_ids: List[str],
        *,
        artifact_name: str = "operator_files",
    ) -> None:
        """Публикует артефакт со списком ID прикреплённых файлов."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=artifact_name,
            parts=[DataPart(data={"file_ids": file_ids})],
        )
        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
            append=False,
            last_chunk=True,
        )
        await self._publish(event)

    async def emit_artifact(
        self,
        data: str,
        name: str = "artifact",
    ) -> None:
        """Публикует артефакт (JSON данные)."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=name,
            parts=[DataPart(data={"content": data})],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_ui_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        event_id: Optional[str] = None,
        version: str = "1.0.0",
        timestamp: str,
        source: str = "assistant",
        correlation_id: Optional[str] = None,
    ) -> None:
        """Публикует UI событие в A2A stream как artifact 'ui_event'."""
        normalized_event_id = event_id or str(uuid.uuid4())
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name="ui_event",
            parts=[
                DataPart(
                    data={
                        "id": normalized_event_id,
                        "type": event_type,
                        "payload": payload,
                        "version": version,
                        "timestamp": timestamp,
                        "source": source,
                        "correlation_id": correlation_id,
                    }
                )
            ],
        )
        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
            append=False,
            last_chunk=True,
        )
        await self._publish(event)

    async def emit_breakpoint(
        self,
        node_id: str,
        node_type: str,
        state_snapshot: Dict[str, Any],
    ) -> None:
        """
        Публикует событие срабатывания breakpoint.

        Использует TaskState.input_required (ждём "Continue" от пользователя).
        Breakpoint отличается от interrupt по metadata.breakpoint=true.
        """
        event = TaskStatusUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            status=TaskStatus(
                state=TaskState.input_required,
                message=self._create_message(f"Breakpoint at node '{node_id}'"),
            ),
            final=True,
            metadata={
                "breakpoint": True,
                "node_id": node_id,
                "node_type": node_type,
                "state_snapshot": state_snapshot,
            },
        )
        await self._publish(event)

    @abstractmethod
    async def _publish(self, event: Any) -> None:
        """Публикует событие. Реализуется в наследниках."""
        pass


class BaseSubscriber(ABC):
    """
    Базовый класс для подписки на события.

    Реализации:
    - RedisSubscriber: подписка на Redis Pub/Sub
    - InMemorySubscriber: чтение из памяти
    """

    @abstractmethod
    async def subscribe(
        self,
        task_id: str,
        timeout: float = 300.0,
    ) -> AsyncIterator[StreamEvent]:
        """Подписывается на события задачи."""
        pass

    async def collect(
        self,
        task_id: str,
        timeout: float = 300.0,
    ) -> List[StreamEvent]:
        """Собирает все события до финального."""
        events: List[StreamEvent] = []
        async for event in self.subscribe(task_id, timeout):
            events.append(event)
        return events


__all__ = ["BaseEmitter", "BaseSubscriber", "StreamEvent"]

