"""
Универсальный TestRunner для evaluation.

Тестирует любой callable: (ExecutionState) -> ExecutionState
- запуск flow (target_callable)
- BaseNode.run

Поддерживает все комбинации input x check.
"""

from __future__ import annotations

import importlib
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date
from typing import TYPE_CHECKING, ClassVar, cast

from a2a.types import TaskArtifactUpdateEvent, TextPart

import core.tracing.attributes as trace_attributes
from apps.flows.src.container_contracts import FlowEvaluationFactoryProtocol, ToolRegistryProtocol
from apps.flows.src.models import NodeConfig, TestCaseConfig
from apps.flows.src.models.evaluation_result import (
    EvaluationDialogMessage,
    EvaluationJudgeResult,
    EvaluationLLMResponse,
    EvaluationRunnerEvent,
    EvaluationScores,
)
from apps.flows.src.models.flow_config import (
    CheckConfig,
    CheckType,
    InputConfig,
    InputType,
    TestTurn,
)
from core.billing import get_billing_service
from core.billing.service import BALANCE_BLOCK_OPERATION_LLM
from core.clients.llm import get_llm
from core.clients.llm.messages import LLMToolCall
from core.company_ai import COST_ORIGIN_COMPANY, AICapability, resolve_llm_for_capability
from core.context import get_context
from core.llm_context import LLMContextPatch
from core.logging import get_logger
from core.models.billing_models import UsageType
from core.state import ExecutionState
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

if TYPE_CHECKING:
    from apps.flows.src.db import NodeRepository
    from apps.flows.src.runners.remote import RemoteCodeRunner

logger = get_logger(__name__)

ScoresType = dict[str, float]
StringChecker = Callable[[JsonObject, str], bool]

TEST_COMPLETE_MARKER = "[TEST_COMPLETE]"
LOOP_DETECTION_WINDOW = 3


class TestRunner:
    """
    Универсальный runner для тестирования.

    Тестирует callable: (ExecutionState) -> ExecutionState.
    Поддерживает агентов и отдельные ноды.
    """

    __test__: ClassVar[bool] = False

    def __init__(
        self,
        target_id: str,
        target_callable: Callable[[ExecutionState], Awaitable[ExecutionState]],
        run_date: date,
        iteration: int,
        *,
        flow_factory: FlowEvaluationFactoryProtocol | None = None,
        node_repository: "NodeRepository | None" = None,
        tool_registry: ToolRegistryProtocol | None = None,
    ):
        self.target_id: str = target_id
        self.target_callable: Callable[[ExecutionState], Awaitable[ExecutionState]] = target_callable
        self.run_date: date = run_date
        self.iteration: int = iteration
        self._flow_factory: FlowEvaluationFactoryProtocol | None = flow_factory
        self._node_repository: NodeRepository | None = node_repository
        self._tool_registry: ToolRegistryProtocol | None = tool_registry

    def _get_code_runner(self, language: str) -> "RemoteCodeRunner":
        if self._flow_factory is not None:
            container = self._flow_factory.container
            return container.get_code_runner(language=language)

        raise RuntimeError("Evaluation inline code requires FlowContainer-backed remote code runner")

    async def run(
        self,
        test_case: TestCaseConfig,
        test_case_id: str,
        task_id: str | None = None,
    ) -> AsyncIterator[EvaluationRunnerEvent]:
        """
        Запускает тест со стримингом.

        Для каждого turn:
        1. Генерирует input (text/function/node)
        2. Вызывает target_callable(state)
        3. Проверяет результат (string/function/node)
        """
        elapsed = self._measure_time()
        if task_id is None:
            task_id = str(uuid.uuid4())

        turns_count = 0
        step_scores: ScoresType = {}
        initial_state_dict: JsonObject = dict(test_case.initial_state or {})

        context_id = str(uuid.uuid4())
        session_id = f"{self.target_id}:{context_id}"

        execution_state = ExecutionState.model_validate(
            {
                **initial_state_dict,
                "task_id": task_id,
                "context_id": context_id,
                "session_id": session_id,
                "user_id": "evaluation_runner",
                "content": "",
            }
        )
        response = ""
        dialog: list[EvaluationDialogMessage] = []

        try:
            if not test_case.turns:
                yield {
                    "type": "result",
                    "status": "error",
                    "duration_ms": elapsed(),
                    "error": "No turns provided",
                    "task_id": task_id,
                    "context_id": context_id,
                }
                return

            # Определяем тип теста по первому turn
            first_turn = test_case.turns[0]
            is_tester_judge_dialog = (
                first_turn.input.type == InputType.NODE
                and first_turn.check
                and first_turn.check.type == CheckType.NODE
            )

            if is_tester_judge_dialog:
                async for event in self._run_tester_judge_dialog(
                    test_case, first_turn, task_id, elapsed, execution_state
                ):
                    yield event
                return

            # Обычный тест с шагами
            for i, turn in enumerate(test_case.turns):
                turns_count += 1

                input_text, files = await self._get_input(turn.input, execution_state)

                if not input_text and not files:
                    yield {
                        "type": "result",
                        "status": "error",
                        "duration_ms": elapsed(),
                        "error": f"Turn {i + 1}: no input",
                        "task_id": task_id,
                        "context_id": context_id,
                    }
                    return

                user_content = input_text or "[file]"
                yield {"type": "user", "content": user_content}

                execution_state.content = input_text or ""
                execution_state = await self.target_callable(execution_state)

                response = execution_state.response or ""

                dialog.append(EvaluationDialogMessage(role="user", content=user_content))
                dialog.append(EvaluationDialogMessage(role="assistant", content=response))

                yield {"type": "assistant", "content": response}

                # Проверка
                if turn.check:
                    check_result = await self._execute_check(
                        turn.check, execution_state, response, dialog
                    )

                    step_key = f"step_{i + 1}"
                    step_scores[step_key] = check_result.get("result", 10.0)

                    for k, v in check_result.items():
                        if k != "result" and k not in step_scores:
                            step_scores[k] = v

                    if not self._scores_passed(check_result):
                        yield {
                            "type": "result",
                            "status": "failed",
                            "duration_ms": elapsed(),
                            "turns_count": turns_count,
                            "scores": step_scores,
                            "dialog": dialog,
                            "error": f"Step {i + 1} check failed",
                            "task_id": task_id,
                            "context_id": context_id,
                        }
                        return

            # Все шаги пройдены
            if not step_scores:
                step_scores = {"result": 10.0}

            yield {
                "type": "result",
                "status": "passed",
                "duration_ms": elapsed(),
                "turns_count": turns_count,
                "scores": step_scores,
                "dialog": dialog,
                "task_id": task_id,
                "context_id": context_id,
            }

        except Exception as e:
            logger.exception(f"Error running test {test_case_id}")
            yield {
                "type": "result",
                "status": "error",
                "duration_ms": elapsed(),
                "turns_count": turns_count,
                "error": str(e),
                "task_id": task_id,
                "context_id": context_id,
            }

    async def _run_tester_judge_dialog(
        self,
        test_case: TestCaseConfig,
        turn: TestTurn,
        task_id: str,
        elapsed: Callable[[], int],
        execution_state: ExecutionState,
    ) -> AsyncIterator[EvaluationRunnerEvent]:
        """Диалог нода-тестер / нода-судья против тестируемого flow."""
        dialog: list[EvaluationDialogMessage] = []
        turns = 0

        tester_config = await self._get_node_config(turn.input, execution_state)

        # Первое сообщение тестера
        tester_messages: list[JsonObject] = []
        tester_response = await self._invoke_node(
            tester_config,
            tester_messages,
            "Начни тестирование. Напиши первое сообщение как пользователь.",
        )

        while turns < test_case.max_turns:
            turns += 1

            if TEST_COMPLETE_MARKER in tester_response:
                break

            dialog.append(EvaluationDialogMessage(role="tester", content=tester_response))
            yield {"type": "user", "content": f"[TESTER] {tester_response}"}

            execution_state.content = tester_response
            execution_state = await self.target_callable(execution_state)

            flow_response = execution_state.response or ""

            dialog.append(EvaluationDialogMessage(role="assistant", content=flow_response))
            yield {"type": "assistant", "content": flow_response}

            if self._detect_loop(dialog):
                yield {
                    "type": "result",
                    "status": "error",
                    "duration_ms": elapsed(),
                    "turns_count": turns,
                    "error": "Loop detected",
                    "task_id": task_id,
                    "context_id": execution_state.context_id,
                }
                return

            tester_messages.append({"role": "assistant", "content": tester_response})
            tester_messages.append({"role": "user", "content": flow_response})

            tester_response = await self._invoke_node(
                tester_config, tester_messages, flow_response
            )

        # Оценка судьей
        scores, feedback, passed = await self._judge_dialog(turn.check, dialog, execution_state)

        yield {
            "type": "result",
            "status": "passed" if passed else "failed",
            "duration_ms": elapsed(),
            "turns_count": turns,
            "scores": scores,
            "judge_feedback": feedback,
            "dialog": dialog,
            "task_id": task_id,
            "context_id": execution_state.context_id,
        }

    async def _get_input(
        self, input_config: InputConfig, execution_state: ExecutionState
    ) -> tuple[str | None, list[JsonObject] | None]:
        """Получает input на основе конфигурации."""
        if input_config.type == InputType.TEXT:
            return input_config.value, None

        if input_config.type == InputType.INLINE_CODE:
            runner = self._get_code_runner(input_config.language)
            result = await runner.execute_tool(
                input_config.value,
                {},
                execution_state,
                entrypoint=input_config.entrypoint,
            )
            return str(result), None

        return input_config.value, None

    async def _execute_check(
        self,
        check_config: CheckConfig,
        execution_state: ExecutionState,
        response: str,
        dialog: list[EvaluationDialogMessage],
    ) -> dict[str, float]:
        """Выполняет проверку. Всегда возвращает Dict[str, float] (0-10)."""
        state_dict = require_json_object(
            execution_state.model_dump(mode="json", exclude_none=False),
            "execution_state",
        )

        if check_config.type == CheckType.STRING:
            result = self._execute_string_checker(check_config.value, state_dict, response)
            return {"result": 10.0 if result else 0.0}

        if check_config.type == CheckType.INLINE_CODE:
            runner = self._get_code_runner(check_config.language)
            dialog_payload: list[JsonValue] = [
                require_json_object(message.model_dump(mode="json"), "evaluation.dialog[]")
                for message in dialog
            ]
            result = await runner.execute_tool(
                check_config.value,
                {"state": state_dict, "response": response, "dialog": dialog_payload},
                execution_state,
                entrypoint=check_config.entrypoint,
            )
            return self._normalize_check_result(result)

        if check_config.type == CheckType.NODE:
            scores, _, passed = await self._judge_dialog(check_config, dialog, execution_state)
            scores["result"] = 10.0 if passed else 0.0
            return scores

        raise ValueError(f"Unknown check type: {check_config.type}")

    def _normalize_check_result(self, result: JsonValue) -> dict[str, float]:
        """
        Нормализует результат проверки к единой структуре: Dict[str, float] (0-10).

        True -> {"result": 10.0}
        False -> {"result": 0.0}
        число -> {"result": число}
        dict -> преобразует все значения: True->10, False->0, числа остаются
        """
        if isinstance(result, bool):
            return {"result": 10.0 if result else 0.0}

        if isinstance(result, (int, float)):
            return {"result": float(result)}

        if isinstance(result, dict):
            normalized: dict[str, float] = {}
            for k, v in result.items():
                if isinstance(v, bool):
                    normalized[k] = 10.0 if v else 0.0
                elif isinstance(v, (int, float)):
                    normalized[k] = float(v)
                elif v is None:
                    normalized[k] = 0.0
            return normalized if normalized else {"result": 10.0}

        return {"result": 10.0}

    def _execute_string_checker(
        self, checker: str, state: JsonObject, response: str
    ) -> bool:
        """Выполняет строковую проверку."""
        if checker.startswith("contains:"):
            words = checker[9:].split("|")
            response_lower = response.lower()
            return any(w.strip().lower() in response_lower for w in words)

        if checker.startswith("not_contains:"):
            words = checker[13:].split("|")
            response_lower = response.lower()
            return not any(w.strip().lower() in response_lower for w in words)

        if checker.startswith("regex:"):
            pattern = checker[6:]
            return bool(re.search(pattern, response, re.IGNORECASE))

        if checker.startswith("length:"):
            return self._check_length(checker[7:], response)

        if checker.startswith("state:"):
            return self._check_state_expression(checker[6:], state)

        # Python функция по пути модуля
        fn = self._import_function(checker)
        return fn(state, response)

    def _check_length(self, spec: str, response: str) -> bool:
        """Проверяет длину ответа."""
        length = len(response)

        if "-" in spec:
            parts = spec.split("-")
            if parts[0] == "":
                return length <= int(parts[1])
            elif parts[1] == "":
                return length >= int(parts[0])
            else:
                return int(parts[0]) <= length <= int(parts[1])
        else:
            return length >= int(spec)

    def _check_state_expression(self, expression: str, state: JsonObject) -> bool:
        """Проверяет выражение над state."""
        operators = ["==", "!=", ">=", "<=", ">", "<"]
        op = None
        for o in operators:
            if o in expression:
                op = o
                break

        if not op:
            return self._get_nested_value(state, expression.strip()) is not None

        parts = expression.split(op)
        if len(parts) != 2:
            return False

        field = parts[0].strip()
        expected_raw = parts[1].strip()
        expected: JsonValue = expected_raw

        if expected_raw.startswith(("'", '"')) and expected_raw.endswith(("'", '"')):
            expected = expected_raw[1:-1]
        elif expected_raw == "true":
            expected = True
        elif expected_raw == "false":
            expected = False
        elif expected_raw in ("null", "None"):
            expected = None
        else:
            try:
                expected = int(expected_raw)
            except ValueError:
                try:
                    expected = float(expected_raw)
                except ValueError:
                    pass

        actual = self._get_nested_value(state, field)

        if op == "==":
            return actual == expected
        elif op == "!=":
            return actual != expected
        elif isinstance(actual, bool) or isinstance(expected, bool):
            return False
        elif isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            if op == ">":
                return actual > expected
            elif op == "<":
                return actual < expected
            elif op == ">=":
                return actual >= expected
            elif op == "<=":
                return actual <= expected
        elif isinstance(actual, str) and isinstance(expected, str):
            if op == ">":
                return actual > expected
            elif op == "<":
                return actual < expected
            elif op == ">=":
                return actual >= expected
            elif op == "<=":
                return actual <= expected

        return False

    def _get_nested_value(self, data: JsonObject, path: str) -> JsonValue:
        """Получает значение по вложенному пути (a.b.c)."""
        keys = path.split(".")
        value: JsonValue = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    def _import_function(self, function_path: str) -> StringChecker:
        """Импортирует функцию по полному пути модуля."""
        module_path, func_name = function_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        checker = cast(StringChecker, getattr(module, func_name))
        if not callable(checker):
            raise TypeError(f"Checker '{function_path}' is not callable")
        return checker

    async def _get_node_config(
        self, input_config: InputConfig, execution_state: ExecutionState | None = None
    ) -> NodeConfig:
        """Получает конфигурацию ноды: inline dict, из графа flow по session/skill/version или node_repository."""
        if input_config.node:
            return NodeConfig.model_validate(input_config.node)

        node_id = input_config.value
        if node_id and execution_state:
            if self._flow_factory is None:
                raise ValueError("flow_factory is required for NODE input lookup")
            nodes_map = await self._flow_factory.get_effective_nodes_map(
                execution_state.session_flow_id,
                execution_state.branch_id,
                execution_state.flow_config_version,
            )
            node_dict = nodes_map.get(node_id)
            if node_dict is not None:
                config = require_json_object(node_dict, f"flow.nodes.{node_id}")
                config["node_id"] = node_id
                return NodeConfig.model_validate(config)

        if node_id:
            if self._node_repository is None:
                raise ValueError("node_repository is required for NODE input lookup")
            node_config = await self._node_repository.get(node_id)
            if node_config is not None:
                return node_config

        raise ValueError(
            "node config is required for NODE input type: "
            + f"neither 'node' inline config nor flow node '{node_id}' found"
        )

    async def _invoke_node(
        self,
        node_config: NodeConfig,
        messages: list[JsonObject],
        last_message: str,
    ) -> str:
        """Вызывает ноду (tester/judge) через LLM."""
        system_prompt = node_config.prompt or "Ты тестер. Веди диалог с агентом."

        llm_messages: list[JsonObject] = [{"role": "system", "content": system_prompt}]
        llm_messages.extend(messages)
        if last_message and not messages:
            llm_messages.append({"role": "user", "content": last_message})

        tools_for_llm: list[JsonObject] | None = None
        if node_config.tools:
            if self._tool_registry is None:
                raise ValueError("tool_registry is required for NODE evaluation tools")
            tools = await self._tool_registry.create_tools(node_config.tools)
            tools_for_llm = [tool.to_openai_schema() for tool in tools]

        request_ctx = get_context()
        if request_ctx is None:
            raise ValueError(
                "Для evaluation LLM нужен Context запроса (user, active_company). "
                + "Запуск evaluation tester/judge только из обработчика с установленным контекстом."
            )
        result = await self._invoke_evaluation_llm(
            messages=llm_messages,
            tools=tools_for_llm,
            task_id=str(uuid.uuid4()),
            context_id="evaluation",
            llm_context=node_config.llm_context or LLMContextPatch(profile="compact"),
        )

        return result.content.strip()

    async def _judge_dialog(
        self,
        check_config: CheckConfig | None,
        dialog: list[EvaluationDialogMessage],
        execution_state: ExecutionState | None = None,
    ) -> tuple[ScoresType, str | None, bool]:
        """Вызывает агента-судью для оценки диалога."""
        if not check_config:
            return {"result": 10.0}, None, True

        judge_config = await self._get_judge_config(check_config, execution_state)

        dialog_text = "\n".join(f"{msg.role.upper()}: {msg.content}" for msg in dialog)

        judge_prompt = judge_config.prompt or "Оцени диалог от 0 до 10."
        system_message = f"""{judge_prompt}

Диалог для оценки:
{dialog_text}

Верни JSON:
{{"scores": {{"quality": 8}}, "total_score": 8, "passed": true, "feedback": "..."}}
"""

        request_ctx = get_context()
        if request_ctx is None:
            raise ValueError(
                "Для evaluation LLM нужен Context запроса (user, active_company). "
                + "Запуск evaluation tester/judge только из обработчика с установленным контекстом."
            )
        result = await self._invoke_evaluation_llm(
            messages=[{"role": "user", "content": system_message}],
            tools=None,
            task_id=str(uuid.uuid4()),
            context_id="evaluation",
            llm_context=judge_config.llm_context or LLMContextPatch(profile="compact"),
        )

        response_text = result.content

        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            judge_result = EvaluationJudgeResult.model_validate(
                parse_json_object(response_text[start:end], "evaluation.judge_response")
            )
            if judge_result.scores:
                scores = self._normalize_check_result(judge_result.scores)
            else:
                judge_passed = True if judge_result.passed is None else judge_result.passed
                scores = {"result": 10.0 if judge_passed else 0.0}
            passed = judge_result.passed
            if passed is None:
                passed = self._scores_passed(scores)
            return scores, judge_result.feedback, passed

        raise ValueError(f"Judge response is not valid JSON: {response_text}")

    async def _invoke_evaluation_llm(
        self,
        *,
        messages: list[JsonObject],
        tools: list[JsonObject] | None,
        task_id: str,
        context_id: str,
        llm_context: LLMContextPatch | None = None,
    ) -> EvaluationLLMResponse:
        actx = get_context()
        if actx is None or actx.active_company is None:
            raise ValueError("Контекст с active_company обязателен для evaluation LLM")
        if not str(actx.user.user_id).strip():
            raise ValueError("Контекст с user обязателен для evaluation LLM")

        uid = str(actx.user.user_id).strip()
        resolved = resolve_llm_for_capability(
            AICapability.LLM_CHAT,
            include_platform_default=True,
        )
        if resolved is None:
            raise ValueError(
                "evaluation LLM: platform default для capability=llm_chat не настроен"
            )
        llm = get_llm(
            model_name=resolved.model,
            provider=resolved.provider,
            api_key=resolved.api_key,
            base_url=resolved.base_url,
            folder_id=resolved.folder_id,
            extra_request_headers=resolved.extra_request_headers,
            extra_request_body=resolved.extra_request_body,
            fallback_models=list(resolved.fallback_models or ()) or None,
        )
        if resolved.cost_origin != COST_ORIGIN_COMPANY:
            await get_billing_service().require_balance_for_billable_operation(
                actx.active_company.company_id,
                uid,
                operation_code=BALANCE_BLOCK_OPERATION_LLM,
                notification_service="flows",
            )

        trace_extra = {
            trace_attributes.ATTR_USER_ID: uid,
            trace_attributes.ATTR_TENANT_COMPANY_ID: actx.active_company.company_id,
        }
        async with traced_operation(
            "flows.evaluation.llm",
            event_type="llm.invoke",
            operation_category="llm",
            billing_usage_type=UsageType.LLM_REQUEST.value,
            billing_resource_name=resolved.billing_resource_name,
            billing_quantity=1,
            billing_pending_settlement=True,
            extra_attributes=trace_extra,
        ) as span:
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls: list[LLMToolCall] | None = None
            input_tokens = 0
            output_tokens = 0

            async for event in llm.stream(
                messages=messages,
                tools=tools or [],
                task_id=task_id,
                context_id=context_id,
                llm_context=llm_context,
            ):
                if isinstance(event, TaskArtifactUpdateEvent):
                    artifact_name = event.artifact.name
                    if event.artifact.parts:
                        for part in event.artifact.parts:
                            if isinstance(part.root, TextPart):
                                text = part.root.text
                                if artifact_name == "reasoning":
                                    reasoning_parts.append(text)
                                else:
                                    content_parts.append(text)
                    continue
                if event.status.message and event.status.message.metadata:
                    metadata = require_json_object(
                        event.status.message.metadata,
                        "evaluation.llm_event.metadata",
                    )
                    raw_tool_calls = metadata.get("tool_calls")
                    if raw_tool_calls is not None:
                        if not isinstance(raw_tool_calls, list):
                            raise ValueError("evaluation.llm_event.metadata.tool_calls must be a list")
                        parsed_tool_calls: list[LLMToolCall] = []
                        for index, item in enumerate(raw_tool_calls):
                            if not isinstance(item, dict):
                                raise ValueError(
                                    "evaluation.llm_event.metadata.tool_calls"
                                    + f"[{index}] must be an object"
                                )
                            parsed_tool_calls.append(LLMToolCall.model_validate(item))
                        tool_calls = parsed_tool_calls

                    raw_usage = metadata.get("usage")
                    if raw_usage is not None:
                        usage = require_json_object(raw_usage, "evaluation.llm_event.metadata.usage")
                        raw_input_tokens = usage.get("input_tokens", 0)
                        raw_output_tokens = usage.get("output_tokens", 0)
                        if not isinstance(raw_input_tokens, int) or isinstance(raw_input_tokens, bool):
                            raise ValueError(
                                "evaluation.llm_event.metadata.usage.input_tokens must be an int"
                            )
                        if not isinstance(raw_output_tokens, int) or isinstance(raw_output_tokens, bool):
                            raise ValueError(
                                "evaluation.llm_event.metadata.usage.output_tokens must be an int"
                            )
                        input_tokens = raw_input_tokens
                        output_tokens = raw_output_tokens

            total_tokens = input_tokens + output_tokens
            if total_tokens > 0:
                span.set_attribute(trace_attributes.ATTR_BILLING_QUANTITY, total_tokens)
                span.set_attribute(trace_attributes.ATTR_LLM_INPUT_TOKENS, input_tokens)
                span.set_attribute(trace_attributes.ATTR_LLM_OUTPUT_TOKENS, output_tokens)

            return EvaluationLLMResponse(
                content="".join(content_parts),
                reasoning="".join(reasoning_parts) if reasoning_parts else None,
                tool_calls=tool_calls,
            )

    async def _get_judge_config(
        self, check_config: CheckConfig, execution_state: ExecutionState | None = None
    ) -> NodeConfig:
        """Получает конфигурацию судьи: inline dict, из графа flow по session/skill/version или node_repository."""
        if check_config.node:
            return NodeConfig.model_validate(check_config.node)

        node_id = check_config.value
        if node_id and execution_state:
            if self._flow_factory is None:
                raise ValueError("flow_factory is required for NODE check lookup")
            nodes_map = await self._flow_factory.get_effective_nodes_map(
                execution_state.session_flow_id,
                execution_state.branch_id,
                execution_state.flow_config_version,
            )
            node_dict = nodes_map.get(node_id)
            if node_dict is not None:
                config = require_json_object(node_dict, f"flow.nodes.{node_id}")
                config["node_id"] = node_id
                return NodeConfig.model_validate(config)

        if node_id:
            if self._node_repository is None:
                raise ValueError("node_repository is required for NODE check lookup")
            node_config = await self._node_repository.get(node_id)
            if node_config is not None:
                return node_config

        raise ValueError(
            "node config is required for NODE check type: "
            + f"neither 'node' inline config nor flow node '{node_id}' found"
        )

    def _scores_passed(self, scores: EvaluationScores) -> bool:
        """Все scores должны быть >= 5.0."""
        for v in scores.values():
            if isinstance(v, bool):
                if not v:
                    return False
            elif v < 5.0:
                return False
        return True

    def _detect_loop(self, dialog: list[EvaluationDialogMessage]) -> bool:
        """Определяет зацикливание в диалоге."""
        if len(dialog) < LOOP_DETECTION_WINDOW * 2:
            return False

        recent = [message.content for message in dialog[-LOOP_DETECTION_WINDOW:]]
        previous = [
            message.content
            for message in dialog[-LOOP_DETECTION_WINDOW * 2 : -LOOP_DETECTION_WINDOW]
        ]

        return recent == previous

    def _measure_time(self) -> Callable[[], int]:
        """Создает функцию измерения времени в мс."""
        start = time.perf_counter()
        return lambda: int((time.perf_counter() - start) * 1000)
