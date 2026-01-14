"""
Runner для всех тест-кейсов.

Любой тест = список ходов (turns): [{input, check}, ...]

Поддерживаемые типы input:
- text: строка для отправки
- function: inline Python функция генерирующая input
- agent: агент генерирующий сообщения

Поддерживаемые типы check:
- string: contains:, regex:, state:, length:, not_contains:
- function: inline Python функция проверки
- agent: агент-судья оценивающий результат
"""

import importlib
import json
import os
import re
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

from apps.agents.src.container import get_container
from apps.agents.src.eval import compile_function
from apps.agents.src.models import NodeConfig, TestCaseConfig
from apps.agents.src.models.agent_config import CheckConfig, CheckType, InputConfig, InputType, TestTurn
from apps.agents.src.tasks.llm_tasks import invoke_llm
from core.logging import get_logger

from .base import BaseTestRunner

logger = get_logger(__name__)

ScoresType = Dict[str, Union[float, bool]]

TEST_COMPLETE_MARKER = "[TEST_COMPLETE]"
LOOP_DETECTION_WINDOW = 3


class DialogTestRunner(BaseTestRunner):
    """Унифицированный runner для всех тест-кейсов."""

    async def run(
        self, test_case: TestCaseConfig, test_case_id: str, task_id: Optional[str] = None
    ):
        """
        Запускает тест со стримингом.

        Обрабатывает все типы через turns:
        - text/string: простой диалог
        - function/function: тест через Python функции
        - agent/agent: агентский диалог с судьёй
        """
        elapsed = self.measure_time()
        if task_id is None:
            task_id = str(uuid.uuid4())

        session_id = None
        turns_count = 0
        step_scores: ScoresType = {}
        state: Dict[str, Any] = {}
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
                # Agent-to-agent тест
                async for event in self._run_agent_test(
                    test_case, first_turn, task_id, elapsed
                ):
                    yield event
                return

            # Обычный тест с шагами
            for i, turn in enumerate(test_case.turns):
                turns_count += 1

                # Получаем input
                input_text, files = await self._get_input(turn.input)

                if not input_text and not files:
                    yield {
                        "type": "result",
                        "status": "error",
                        "duration_ms": elapsed(),
                        "error": f"Turn {i + 1}: no input",
                        "task_id": task_id,
                    }
                    return

                yield {"type": "user", "content": input_text or "[file]"}

                result = await self.send_message(
                    content=input_text or "",
                    files=files,
                    session_id=session_id,
                    task_id=task_id,
                )

                session_id = result.get("session_id", session_id)
                response = result.get("response", "")
                state = result.get("state", {})

                dialog.append({"role": "user", "content": input_text})
                dialog.append({"role": "assistant", "content": response})

                yield {"type": "assistant", "content": response}

                # Проверка
                if turn.check:
                    check_result = await self._execute_check(turn.check, state, response, dialog)

                    if isinstance(check_result, dict):
                        step_scores[f"step_{i + 1}"] = check_result.get("result", True)
                        if not self._scores_passed(check_result):
                            yield {
                                "type": "result",
                                "status": "failed",
                                "duration_ms": elapsed(),
                                "turns_count": turns_count,
                                "scores": {**step_scores, **check_result},
                                "error": f"Step {i + 1} check failed",
                                "task_id": task_id,
                            }
                            return
                    else:
                        step_scores[f"step_{i + 1}"] = check_result
                        if not check_result:
                            yield {
                                "type": "result",
                                "status": "failed",
                                "duration_ms": elapsed(),
                                "turns_count": turns_count,
                                "scores": step_scores,
                                "error": f"Step {i + 1} check failed",
                                "task_id": task_id,
                            }
                            return

            # Все шаги пройдены
            if not step_scores:
                step_scores = {"result": True}

            yield {
                "type": "result",
                "status": "passed",
                "duration_ms": elapsed(),
                "turns_count": turns_count,
                "scores": step_scores,
                "task_id": task_id,
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
            }

    async def _run_agent_test(
        self,
        test_case: TestCaseConfig,
        turn: TestTurn,
        task_id: str,
        elapsed: Callable[[], int],
    ):
        """Запускает agent-to-agent тест."""
        session_id = f"eval:{self.agent_id}:{uuid.uuid4()}"
        dialog: List[Dict[str, Any]] = []
        turns = 0

        # Загружаем тестера
        tester_config = await self._get_node_config(turn.input)
        if not tester_config:
            yield {
                "type": "result",
                "status": "error",
                "duration_ms": elapsed(),
                "error": "No tester agent config",
                "task_id": task_id,
            }
            return

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

            agent_result = await self.send_message(
                content=tester_response,
                session_id=session_id,
                is_resume=turns > 1,
                task_id=task_id,
            )
            agent_response = agent_result.get("response", "")

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
                }
                return

            tester_messages.append({"role": "assistant", "content": tester_response})
            tester_messages.append({"role": "user", "content": agent_response})

            tester_response = await self._invoke_node(
                tester_config, tester_messages, agent_response
            )

        # Оценка судьёй
        scores, feedback, passed = await self._judge_dialog(turn.check, dialog)

        yield {
            "type": "result",
            "status": "passed" if passed else "failed",
            "duration_ms": elapsed(),
            "turns_count": turns,
            "scores": scores,
            "judge_feedback": feedback,
            "dialog": dialog,
            "task_id": task_id,
        }

    async def _get_input(
        self, input_config: InputConfig
    ) -> tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """Получает input на основе конфигурации."""
        if input_config.type == InputType.TEXT:
            return input_config.value, None

        if input_config.type == InputType.FUNCTION:
            fn = compile_function(input_config.value, "generate")
            return fn(), None

        # InputType.NODE - не должен попадать сюда для обычных тестов
        return input_config.value, None

    async def _execute_check(
        self,
        check_config: CheckConfig,
        state: Dict[str, Any],
        response: str,
        dialog: List[Dict[str, Any]],
    ) -> Union[bool, Dict[str, Any]]:
        """Выполняет проверку результата."""
        if check_config.type == CheckType.STRING:
            return self._execute_string_checker(check_config.value, state, response)

        if check_config.type == CheckType.FUNCTION:
            fn = compile_function(check_config.value, "check")
            result = fn(state, response)
            return result

        if check_config.type == CheckType.NODE:
            scores, _, passed = await self._judge_dialog(check_config, dialog)
            return {"result": passed, **scores}

        return True

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

        # Python функция по пути
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
        """Получает значение по пути."""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    def _import_function(self, function_path: str) -> Callable:
        """Импортирует функцию по пути."""
        module_path, func_name = function_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, func_name)

    async def _get_node_config(self, input_config: InputConfig) -> Optional[NodeConfig]:
        """Получает конфигурацию ноды."""
        if input_config.node:
            # Преобразуем dict в NodeConfig
            return NodeConfig(**input_config.node)

        if input_config.value:
            container = get_container()
            return await container.node_repository.get(input_config.value)

        return None

    async def _invoke_node(
        self,
        node_config: NodeConfig,
        messages: List[Dict[str, str]],
        last_message: str,
    ) -> str:
        """Вызывает ноду для генерации ответа."""
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
    ) -> tuple[ScoresType, Optional[str], bool]:
        """Вызывает агента-судью для оценки диалога."""
        if not check_config:
            return {"result": True}, None, True

        judge_config = None
        if check_config.node:
            # Преобразуем dict в NodeConfig
            judge_config = NodeConfig(**check_config.node)
        elif check_config.value:
            container = get_container()
            judge_config = await container.node_repository.get(check_config.value)

        if not judge_config:
            return {"result": True}, None, True

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
            logger.warning(f"Judge LLM task failed: {result.error}")
            return {"result": True}, None, True

        response_text = result.return_value.get("content", "")

        try:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                judge_result = json.loads(response_text[start:end])
                scores = judge_result.get("scores", {})
                if not scores:
                    scores = {"result": judge_result.get("passed", True)}
                feedback = judge_result.get("feedback")
                passed = judge_result.get("passed", self._scores_passed(scores))
                return scores, feedback, passed
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse judge response: {response_text}")

        return {"result": True}, response_text, True

    def _scores_passed(self, scores: ScoresType) -> bool:
        """Определяет пройден ли тест."""
        for v in scores.values():
            if isinstance(v, bool) and not v:
                return False
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
