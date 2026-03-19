"""
Универсальный TestRunner для evaluation.

Тестирует любой callable: (ExecutionState) -> ExecutionState
- Agent.run
- BaseNode.run

Поддерживает все комбинации input x check.
"""

import importlib
import inspect
import json
import re
import time
import uuid
from datetime import date
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from apps.agents.src.container import get_container
from apps.agents.src.eval import compile_function
from apps.agents.src.models import NodeConfig, TestCaseConfig
from apps.agents.src.models.agent_config import CheckConfig, CheckType, InputConfig, InputType, TestTurn
from apps.agents.src.tasks.llm_tasks import invoke_llm
from core.logging import get_logger
from core.state import ExecutionState

logger = get_logger(__name__)

ScoresType = Dict[str, float]

TEST_COMPLETE_MARKER = "[TEST_COMPLETE]"
LOOP_DETECTION_WINDOW = 3


class TestRunner:
    """
    Универсальный runner для тестирования.
    
    Тестирует callable: (ExecutionState) -> ExecutionState.
    Поддерживает агентов и отдельные ноды.
    """

    def __init__(
        self,
        target_id: str,
        target_callable: Callable,
        run_date: date,
        iteration: int,
    ):
        self.target_id = target_id
        self.target_callable = target_callable
        self.run_date = run_date
        self.iteration = iteration

    async def run(
        self,
        test_case: TestCaseConfig,
        test_case_id: str,
        task_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
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
        initial_state_dict = test_case.initial_state or {}
        
        context_id = str(uuid.uuid4())
        session_id = f"{self.target_id}:{context_id}"
        
        execution_state = ExecutionState(
            task_id=task_id,
            context_id=context_id,
            session_id=session_id,
            user_id="evaluation_runner",
            content="",
            **initial_state_dict,
        )
        response = ""
        dialog: List[Dict[str, Any]] = []

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
            is_agent_test = (
                first_turn.input.type == InputType.NODE
                and first_turn.check
                and first_turn.check.type == CheckType.NODE
            )

            if is_agent_test:
                async for event in self._run_agent_test(
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

                yield {"type": "user", "content": input_text or "[file]"}

                execution_state.content = input_text or ""
                execution_state = await self.target_callable(execution_state)

                response = execution_state.response or ""

                dialog.append({"role": "user", "content": input_text})
                dialog.append({"role": "assistant", "content": response})

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

    async def _run_agent_test(
        self,
        test_case: TestCaseConfig,
        turn: TestTurn,
        task_id: str,
        elapsed: Callable[[], int],
        execution_state: ExecutionState,
    ):
        """Запускает agent-to-agent тест."""
        dialog: List[Dict[str, Any]] = []
        turns = 0

        tester_config = await self._get_node_config(turn.input, execution_state)

        # Первое сообщение тестера
        tester_messages: List[Dict[str, str]] = []
        tester_response = await self._invoke_node(
            tester_config,
            tester_messages,
            "Начни тестирование. Напиши первое сообщение как пользователь.",
        )

        while turns < test_case.max_turns:
            turns += 1

            if TEST_COMPLETE_MARKER in tester_response:
                break

            dialog.append({"role": "tester", "content": tester_response})
            yield {"type": "user", "content": f"[TESTER] {tester_response}"}

            execution_state.content = tester_response
            execution_state = await self.target_callable(execution_state)
            
            agent_response = execution_state.response or ""

            dialog.append({"role": "agent", "content": agent_response})
            yield {"type": "assistant", "content": agent_response}

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
            tester_messages.append({"role": "user", "content": agent_response})

            tester_response = await self._invoke_node(
                tester_config, tester_messages, agent_response
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
    ) -> tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """Получает input на основе конфигурации."""
        if input_config.type == InputType.TEXT:
            return input_config.value, None

        if input_config.type == InputType.FUNCTION:
            fn = compile_function(input_config.value, "generate")
            sig = inspect.signature(fn)
            if len(sig.parameters) == 0:
                result = fn()
            else:
                result = fn(execution_state.model_dump())
            return str(result), None

        return input_config.value, None

    async def _execute_check(
        self,
        check_config: CheckConfig,
        execution_state: ExecutionState,
        response: str,
        dialog: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """Выполняет проверку. Всегда возвращает Dict[str, float] (0-10)."""
        state_dict = execution_state.model_dump()
        
        if check_config.type == CheckType.STRING:
            result = self._execute_string_checker(check_config.value, state_dict, response)
            return {"result": 10.0 if result else 0.0}

        if check_config.type == CheckType.FUNCTION:
            fn = compile_function(check_config.value, "check")
            result = fn(state_dict, response)
            return self._normalize_check_result(result)

        if check_config.type == CheckType.NODE:
            scores, _, passed = await self._judge_dialog(check_config, dialog, execution_state)
            scores["result"] = 10.0 if passed else 0.0
            return scores

        raise ValueError(f"Unknown check type: {check_config.type}")

    def _normalize_check_result(self, result: Any) -> Dict[str, float]:
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
            normalized = {}
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
        self, checker: str, state: Dict[str, Any], response: str
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

    def _check_state_expression(self, expression: str, state: Dict[str, Any]) -> bool:
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
        expected = parts[1].strip()

        if expected.startswith(("'", '"')) and expected.endswith(("'", '"')):
            expected = expected[1:-1]
        elif expected == "true":
            expected = True
        elif expected == "false":
            expected = False
        elif expected in ("null", "None"):
            expected = None
        else:
            try:
                expected = int(expected)
            except ValueError:
                try:
                    expected = float(expected)
                except ValueError:
                    pass

        actual = self._get_nested_value(state, field)

        if op == "==":
            return actual == expected
        elif op == "!=":
            return actual != expected
        elif op == ">":
            return actual is not None and actual > expected
        elif op == "<":
            return actual is not None and actual < expected
        elif op == ">=":
            return actual is not None and actual >= expected
        elif op == "<=":
            return actual is not None and actual <= expected

        return False

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Получает значение по вложенному пути (a.b.c)."""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    def _import_function(self, function_path: str) -> Callable:
        """Импортирует функцию по полному пути модуля."""
        module_path, func_name = function_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, func_name)

    async def _get_node_config(
        self, input_config: InputConfig, execution_state: Optional[ExecutionState] = None
    ) -> NodeConfig:
        """Получает конфигурацию ноды: inline dict, из agent_config или из node_repository."""
        if input_config.node:
            return NodeConfig(**input_config.node)
        
        node_id = input_config.value
        if node_id and execution_state:
            agent_nodes = (execution_state.agent_config or {}).get("nodes", {})
            node_dict = agent_nodes.get(node_id)
            if node_dict is not None:
                config = dict(node_dict)
                config.setdefault("node_id", node_id)
                return NodeConfig(**config)
        
        if node_id:
            container = get_container()
            node_config = await container.node_repository.get(node_id)
            if node_config is not None:
                return node_config
        
        raise ValueError(
            f"node config is required for NODE input type: "
            f"neither 'node' inline config nor agent node '{node_id}' found"
        )

    async def _invoke_node(
        self,
        node_config: NodeConfig,
        messages: List[Dict[str, str]],
        last_message: str,
    ) -> str:
        """Вызывает ноду (tester/judge) через LLM."""
        system_prompt = node_config.prompt or "Ты тестер. Веди диалог с агентом."

        llm_messages = [{"role": "system", "content": system_prompt}]
        llm_messages.extend(messages)
        if last_message and not messages:
            llm_messages.append({"role": "user", "content": last_message})

        tools_for_llm = None
        if node_config.tools:
            container = get_container()
            tools = await container.tool_registry.create_tools(node_config.tools)
            tools_for_llm = [tool.to_llm_format() for tool in tools]

        task = await invoke_llm.kiq(
            messages=llm_messages,
            tools=tools_for_llm,
            task_id=str(uuid.uuid4()),
            context_id="evaluation",
        )

        result = await task.wait_result()

        if result.is_err:
            raise RuntimeError(f"LLM task failed: {result.error}")

        return result.return_value.get("content", "").strip()

    async def _judge_dialog(
        self,
        check_config: Optional[CheckConfig],
        dialog: List[Dict[str, Any]],
        execution_state: Optional[ExecutionState] = None,
    ) -> tuple[ScoresType, Optional[str], bool]:
        """Вызывает агента-судью для оценки диалога."""
        if not check_config:
            return {"result": 10.0}, None, True

        judge_config = await self._get_judge_config(check_config, execution_state)

        dialog_text = "\n".join(f"{msg['role'].upper()}: {msg['content']}" for msg in dialog)

        judge_prompt = judge_config.prompt or "Оцени диалог от 0 до 10."
        system_message = f"""{judge_prompt}

Диалог для оценки:
{dialog_text}

Верни JSON:
{{"scores": {{"quality": 8}}, "passed": true, "feedback": "..."}}
"""

        task = await invoke_llm.kiq(
            messages=[{"role": "user", "content": system_message}],
            tools=None,
            task_id=str(uuid.uuid4()),
            context_id="evaluation",
        )

        result = await task.wait_result()

        if result.is_err:
            raise RuntimeError(f"Judge LLM task failed: {result.error}")

        response_text = result.return_value.get("content", "")

        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            judge_result = json.loads(response_text[start:end])
            scores = judge_result.get("scores", {})
            if not scores:
                scores = {"result": 10.0 if judge_result.get("passed", True) else 0.0}
            else:
                scores = self._normalize_check_result(scores)
            feedback = judge_result.get("feedback")
            passed = judge_result.get("passed", self._scores_passed(scores))
            return scores, feedback, passed

        raise ValueError(f"Judge response is not valid JSON: {response_text}")

    async def _get_judge_config(
        self, check_config: CheckConfig, execution_state: Optional[ExecutionState] = None
    ) -> NodeConfig:
        """Получает конфигурацию судьи: inline dict, из agent_config или из node_repository."""
        if check_config.node:
            return NodeConfig(**check_config.node)
        
        node_id = check_config.value
        if node_id and execution_state:
            agent_nodes = (execution_state.agent_config or {}).get("nodes", {})
            node_dict = agent_nodes.get(node_id)
            if node_dict is not None:
                config = dict(node_dict)
                config.setdefault("node_id", node_id)
                return NodeConfig(**config)
        
        if node_id:
            container = get_container()
            node_config = await container.node_repository.get(node_id)
            if node_config is not None:
                return node_config
        
        raise ValueError(
            f"node config is required for NODE check type: "
            f"neither 'node' inline config nor agent node '{node_id}' found"
        )

    def _scores_passed(self, scores: ScoresType) -> bool:
        """Все scores должны быть >= 5.0."""
        for v in scores.values():
            if isinstance(v, (int, float)) and v < 5.0:
                return False
        return True

    def _detect_loop(self, dialog: List[Dict[str, Any]]) -> bool:
        """Определяет зацикливание в диалоге."""
        if len(dialog) < LOOP_DETECTION_WINDOW * 2:
            return False

        recent = [m["content"] for m in dialog[-LOOP_DETECTION_WINDOW:]]
        previous = [
            m["content"] for m in dialog[-LOOP_DETECTION_WINDOW * 2 : -LOOP_DETECTION_WINDOW]
        ]

        return recent == previous

    def _measure_time(self) -> Callable[[], int]:
        """Создает функцию измерения времени в мс."""
        start = time.perf_counter()
        return lambda: int((time.perf_counter() - start) * 1000)
