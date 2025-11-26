"""
OpenTelemetry CallbackHandler для LangChain/LangGraph.

Создает стандартные OpenTelemetry spans для всех событий LangChain,
аналогично Langfuse CallbackHandler, но использует наш TracerProvider.
Записывает трейсы в БД при создании и завершении корневого span.
"""

import logging
from contextvars import Token
from typing import Any, Dict, List, Optional, Set, Union, Sequence
from uuid import UUID
from datetime import datetime, timezone

from opentelemetry import trace, context
from opentelemetry.context import _RUNTIME_CONTEXT
from opentelemetry.trace import Status, StatusCode, Span

import langchain

from langchain_core.callbacks.base import BaseCallbackHandler  # type: ignore
from langchain_core.agents import AgentAction, AgentFinish  # type: ignore
from langchain_core.documents import Document  # type: ignore
from langchain_core.callbacks.base import AsyncCallbackHandler  # type: ignore
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from apps.agents.models.trace_models import TraceInfo, SpanStatus
from apps.agents.container import get_agents_container

logger = logging.getLogger(__name__)

# Control flow exceptions (убрали зависимость от LangGraph)
# GraphBubbleUp больше не используется, оставляем пустой набор
CONTROL_FLOW_EXCEPTION_TYPES: Set[type[BaseException]] = set()


class OpenTelemetryCallbackHandler(AsyncCallbackHandler):
    """
    LangChain CallbackHandler для создания OpenTelemetry spans.

    Создает OTEL spans для всех событий LangChain:
    - Chains (on_chain_start/end)
    - LLMs (on_llm_start/end)
    - Tools (on_tool_start/end)
    - Retrievers (on_retriever_start/end)
    - Agents (on_agent_action/finish)

    Spans автоматически связываются в иерархию через parent_run_id.
    """

    def __init__(self, tracer_name: str = "langchain", update_trace: bool = False):
        """
        Инициализирует callback handler.

        Args:
            tracer_name: Имя tracer'а для получения из TracerProvider
            update_trace: Обновлять ли trace в БД при создании/завершении корневого span
        """
        self.tracer = trace.get_tracer(tracer_name)
        self.runs: Dict[UUID, Span] = {}
        self.context_tokens: Dict[UUID, Token] = {}
        self.update_trace = update_trace
        self.last_trace_id: Optional[str] = None

    def _get_parent_span(self, parent_run_id: Optional[UUID]) -> Optional[Span]:
        """Получить parent span по parent_run_id."""
        if parent_run_id and parent_run_id in self.runs:
            return self.runs[parent_run_id]
        return None

    def _start_span(
        self,
        name: str,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """
        Создать и начать новый span.

        Args:
            name: Имя span'а
            run_id: ID запуска LangChain
            parent_run_id: ID родительского запуска
            attributes: Дополнительные атрибуты

        Returns:
            Созданный span
        """
        # Получаем parent span
        parent_span = self._get_parent_span(parent_run_id)

        # Создаем контекст для span'а
        if parent_span:
            ctx = trace.set_span_in_context(parent_span)
        else:
            ctx = context.get_current()

        # Создаем span
        span = self.tracer.start_span(
            name=name,
            context=ctx,
            attributes=attributes or {},
        )

        # Сохраняем span и его контекст
        self.runs[run_id] = span
        self.context_tokens[run_id] = context.attach(trace.set_span_in_context(span))

        # Сохраняем trace_id для отслеживания
        if hasattr(span, "context"):
            span_ctx = span.context
            if span_ctx and hasattr(span_ctx, "trace_id"):
                self.last_trace_id = format(span_ctx.trace_id, '032x')

        return span

    def _end_span(
        self,
        run_id: UUID,
        status: Optional[StatusCode] = None,
        description: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Завершить span.

        Args:
            run_id: ID запуска LangChain
            status: Статус завершения (SUCCESS/ERROR)
            description: Описание статуса
            attributes: Дополнительные атрибуты
        """
        if run_id not in self.runs:
            logger.warning(f"Span для run_id={run_id} не найден")
            return

        span = self.runs[run_id]

        # Добавляем атрибуты
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, str(value))

        # Устанавливаем статус
        if status is not None:
            span.set_status(Status(status_code=status, description=description))

        # Завершаем span
        span.end()

        # Отвязываем контекст
        token = self.context_tokens.pop(run_id, None)

        if token:
            try:
                # Directly detach from runtime context to avoid error logging
                _RUNTIME_CONTEXT.detach(token)
            except Exception:
                # Context detach can fail in async scenarios - this is expected and safe to ignore
                # The span itself was properly ended and tracing data is correctly captured
                #
                # Examples:
                # 1. Token created in one async task/thread, detached in another
                # 2. Context already detached by framework or other handlers
                # 3. Runtime context state mismatch in concurrent execution
                pass

        # Удаляем span
        del self.runs[run_id]

    def _get_name_from_serialized(
        self, serialized: Optional[Dict[str, Any]], **kwargs: Any
    ) -> str:
        """Извлечь имя из serialized данных LangChain."""
        if "name" in kwargs and kwargs["name"] is not None:
            return str(kwargs["name"])

        if serialized is None:
            return "<unknown>"

        try:
            return str(serialized["name"])
        except (KeyError, TypeError):
            pass

        try:
            return str(serialized["id"][-1])
        except (KeyError, TypeError):
            pass

        return "<unknown>"

    def _parse_trace_attributes_from_metadata(
        self,
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Парсит атрибуты трейса из metadata.

        Аналогично Langfuse: поддерживает langfuse_user_id, langfuse_session_id, langfuse_tags
        """
        attributes: Dict[str, Any] = {}

        if metadata is None:
            return attributes

        if "langfuse_session_id" in metadata and isinstance(
            metadata["langfuse_session_id"], str
        ):
            attributes["session_id"] = metadata["langfuse_session_id"]

        if "langfuse_user_id" in metadata and isinstance(
            metadata["langfuse_user_id"], str
        ):
            attributes["user_id"] = metadata["langfuse_user_id"]

        if "langfuse_tags" in metadata and isinstance(metadata["langfuse_tags"], list):
            attributes["tags"] = [str(tag) for tag in metadata["langfuse_tags"]]

        return attributes

    async def _update_trace_info(
        self,
        trace_id: str,
        name: Optional[str] = None,
        input_data: Optional[Any] = None,
        output_data: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        status: Optional[SpanStatus] = None,
        end_time: Optional[datetime] = None,
    ) -> None:
        """
        Обновляет или создает TraceInfo в БД.

        Args:
            trace_id: ID трейса
            name: Название трейса (название root span)
            input_data: Входные данные
            output_data: Выходные данные
            metadata: Метаданные
            status: Статус трейса
            end_time: Время завершения
        """
        if not self.update_trace:
            return

        try:
            storage = get_agents_container().storage
            trace_key = f"otel:{trace_id}:trace"

            # Получаем существующий trace или создаем новый
            existing_trace_json = await storage.get(trace_key)
            if existing_trace_json:
                trace_info = TraceInfo.model_validate_json(existing_trace_json)
            else:
                # Создаем новый trace
                trace_info = TraceInfo(
                    trace_id=trace_id,
                    name=name or "<unknown>",
                    status=status or SpanStatus.PENDING,
                    start_time=datetime.now(timezone.utc),
                    total_spans=0,
                )

            # Обновляем поля
            if name is not None:
                trace_info.name = name
            if status is not None:
                trace_info.status = status
            if end_time is not None:
                trace_info.end_time = end_time
                if trace_info.start_time:
                    duration = (end_time - trace_info.start_time).total_seconds() * 1000
                    trace_info.duration_ms = duration

            # Обновляем metadata
            if metadata:
                trace_info.metadata.update(metadata)

            # Сохраняем обновленный trace
            await storage.set(trace_key, trace_info.model_dump_json())

            logger.debug(f"📝 Обновлен trace: {trace_id} ({trace_info.name})")

        except Exception as e:
            logger.error(f"Ошибка обновления trace {trace_id}: {e}", exc_info=True)

    # === Chain Events ===

    async def on_chain_start(
        self,
        serialized: Optional[Dict[str, Any]],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Chain start event."""
        name = self._get_name_from_serialized(serialized, **kwargs)
        attributes = {
            "langchain.type": "chain",
            "langchain.run_id": str(run_id),
            "langchain.inputs": str(inputs),
        }

        if tags:
            attributes["langchain.tags"] = ", ".join(tags)
        if metadata:
            attributes["langchain.metadata"] = str(metadata)

        span = self._start_span(
            name=f"Chain: {name}",
            run_id=run_id,
            parent_run_id=parent_run_id,
            attributes=attributes,
        )

        # Если это корневой span (начало трейса), создаем/обновляем TraceInfo
        if parent_run_id is None and self.update_trace:
            # Получаем trace_id из span
            trace_id = self.last_trace_id
            if not trace_id and hasattr(span, "context"):
                span_ctx = span.context
                if span_ctx and hasattr(span_ctx, "trace_id"):
                    trace_id = format(span_ctx.trace_id, '032x')
                    self.last_trace_id = trace_id

            if trace_id:
                trace_attributes = self._parse_trace_attributes_from_metadata(metadata)
                trace_metadata = {}
                if tags:
                    trace_metadata["tags"] = tags
                if metadata:
                    trace_metadata.update(metadata)
                    # Удаляем служебные ключи Langfuse
                    trace_metadata.pop("langfuse_session_id", None)
                    trace_metadata.pop("langfuse_user_id", None)
                    trace_metadata.pop("langfuse_tags", None)
                    trace_metadata.pop("langfuse_prompt", None)

                # Сохраняем input_data для trace
                await self._update_trace_info(
                    trace_id=trace_id,
                    name=name,
                    input_data=inputs,
                    metadata={**trace_metadata, **trace_attributes},
                )

    async def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Chain end event."""
        # Сохраняем trace_id перед завершением span
        trace_id = None
        if run_id in self.runs:
            span = self.runs[run_id]
            if hasattr(span, "context"):
                span_ctx = span.context
                if span_ctx and hasattr(span_ctx, "trace_id"):
                    trace_id = format(span_ctx.trace_id, '032x')

        self._end_span(
            run_id=run_id,
            status=StatusCode.OK,
            attributes={
                "langchain.outputs": str(outputs),
            },
        )

        # Если это корневой span (конец трейса), обновляем TraceInfo
        if parent_run_id is None and self.update_trace and trace_id:
            await self._update_trace_info(
                trace_id=trace_id,
                output_data=outputs,
                status=SpanStatus.SUCCESS,
                end_time=datetime.now(timezone.utc),
            )

    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Chain error event."""
        # Сохраняем trace_id перед завершением span
        trace_id = None
        if run_id in self.runs:
            span = self.runs[run_id]
            if hasattr(span, "context"):
                span_ctx = span.context
                if span_ctx and hasattr(span_ctx, "trace_id"):
                    trace_id = format(span_ctx.trace_id, '032x')

        # LangGraph control flow exceptions - не ошибки
        if type(error) in CONTROL_FLOW_EXCEPTION_TYPES:
            self._end_span(run_id=run_id, status=StatusCode.OK)

            # Обновляем trace как успешный
            if parent_run_id is None and self.update_trace and trace_id:
                await self._update_trace_info(
                    trace_id=trace_id,
                    status=SpanStatus.SUCCESS,
                    end_time=datetime.now(timezone.utc),
                )
        else:
            self._end_span(
                run_id=run_id,
                status=StatusCode.ERROR,
                description=str(error),
                attributes={
                    "langchain.error_type": type(error).__name__,
                },
            )

            # Обновляем trace как ошибочный
            if parent_run_id is None and self.update_trace and trace_id:
                await self._update_trace_info(
                    trace_id=trace_id,
                    status=SpanStatus.ERROR,
                    end_time=datetime.now(timezone.utc),
                    metadata={"error": str(error)},
                )

    # === LLM Events ===

    async def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """LLM start event."""
        name = self._get_name_from_serialized(serialized, **kwargs)
        attributes = {
            "langchain.type": "llm",
            "langchain.run_id": str(run_id),
            "langchain.prompts": str(prompts),
            "langchain.prompt_count": len(prompts),
        }

        # Извлекаем model name
        if "invocation_params" in kwargs:
            model_name = kwargs["invocation_params"].get("model_name")
            if model_name:
                attributes["langchain.model_name"] = model_name

        self._start_span(
            name=f"LLM: {name}",
            run_id=run_id,
            parent_run_id=parent_run_id,
            attributes=attributes,
        )

    async def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Chat model start event."""
        name = self._get_name_from_serialized(serialized, **kwargs)
        attributes = {
            "langchain.type": "chat_model",
            "langchain.run_id": str(run_id),
            "langchain.message_count": len(messages),
        }

        # Извлекаем model name
        if "invocation_params" in kwargs:
            model_name = kwargs["invocation_params"].get("model_name")
            if model_name:
                attributes["langchain.model_name"] = model_name

        self._start_span(
            name=f"ChatModel: {name}",
            run_id=run_id,
            parent_run_id=parent_run_id,
            attributes=attributes,
        )

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """LLM end event."""
        attributes = {}

        # Token usage
        if response.llm_output and "token_usage" in response.llm_output:
            usage = response.llm_output["token_usage"]
            attributes["langchain.tokens.prompt"] = usage.get("prompt_tokens", 0)
            attributes["langchain.tokens.completion"] = usage.get("completion_tokens", 0)
            attributes["langchain.tokens.total"] = usage.get("total_tokens", 0)

        # Generations
        if response.generations:
            attributes["langchain.generation_count"] = len(response.generations)
            # Первая генерация как пример
            if response.generations[0]:
                first_gen = response.generations[0][0]
                if hasattr(first_gen, "text"):
                    attributes["langchain.response_text"] = first_gen.text[:500]

        self._end_span(
            run_id=run_id,
            status=StatusCode.OK,
            attributes=attributes,
        )

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """LLM error event."""
        self._end_span(
            run_id=run_id,
            status=StatusCode.ERROR,
            description=str(error),
            attributes={
                "langchain.error_type": type(error).__name__,
            },
        )

    async def on_llm_new_token(
        self,
        token: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """LLM new token event (streaming)."""
        # Для streaming можно добавить события, пока пропускаем
        pass

    # === Tool Events ===

    async def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Tool start event."""
        name = self._get_name_from_serialized(serialized, **kwargs)
        attributes = {
            "langchain.type": "tool",
            "langchain.run_id": str(run_id),
            "langchain.tool_input": input_str[:500],  # Лимит на длину
        }

        self._start_span(
            name=f"Tool: {name}",
            run_id=run_id,
            parent_run_id=parent_run_id,
            attributes=attributes,
        )

    async def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Tool end event."""
        self._end_span(
            run_id=run_id,
            status=StatusCode.OK,
            attributes={
                "langchain.tool_output": output[:500],
            },
        )

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Tool error event."""
        self._end_span(
            run_id=run_id,
            status=StatusCode.ERROR,
            description=str(error),
            attributes={
                "langchain.error_type": type(error).__name__,
            },
        )

    # === Retriever Events ===

    async def on_retriever_start(
        self,
        serialized: Dict[str, Any],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Retriever start event."""
        name = self._get_name_from_serialized(serialized, **kwargs)
        attributes = {
            "langchain.type": "retriever",
            "langchain.run_id": str(run_id),
            "langchain.query": query[:500],
        }

        self._start_span(
            name=f"Retriever: {name}",
            run_id=run_id,
            parent_run_id=parent_run_id,
            attributes=attributes,
        )

    async def on_retriever_end(
        self,
        documents: Sequence[Document],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Retriever end event."""
        self._end_span(
            run_id=run_id,
            status=StatusCode.OK,
            attributes={
                "langchain.document_count": len(documents),
            },
        )

    async def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Retriever error event."""
        self._end_span(
            run_id=run_id,
            status=StatusCode.ERROR,
            description=str(error),
            attributes={
                "langchain.error_type": type(error).__name__,
            },
        )

    # === Agent Events ===

    async def on_agent_action(
        self,
        action: AgentAction,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Agent action event."""
        if run_id in self.runs:
            span = self.runs[run_id]
            span.add_event(
                name="agent_action",
                attributes={
                    "langchain.agent_action.tool": action.tool,
                    "langchain.agent_action.tool_input": str(action.tool_input)[:500],
                    "langchain.agent_action.log": action.log[:500] if action.log else "",
                },
            )

    async def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Agent finish event."""
        if run_id in self.runs:
            span = self.runs[run_id]
            span.add_event(
                name="agent_finish",
                attributes={
                    "langchain.agent_finish.output": str(finish.return_values)[:500],
                    "langchain.agent_finish.log": finish.log[:500] if finish.log else "",
                },
            )

