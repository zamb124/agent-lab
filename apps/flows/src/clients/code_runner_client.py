"""CodeRunnerClient — RemoteCodeRunner for trusted sandbox_codegen tool."""

from __future__ import annotations

from apps.flows.src.container_state import require_current_container
from apps.flows.src.runners.remote import RemoteCodeRunner
from core.state import ExecutionState
from core.types import JsonObject, JsonValue


class CodeRunnerClient:
    """Исполнение tool-кода в isolated code-runner-*."""

    _runner: RemoteCodeRunner

    def __init__(
        self,
        language: str = "python",
        runner: RemoteCodeRunner | None = None,
    ) -> None:
        self._runner = (
            runner
            if runner is not None
            else require_current_container().get_code_runner(language=language)
        )

    async def execute_tool(
        self,
        code: str,
        args: JsonObject,
        state: ExecutionState,
        *,
        entrypoint: str | None = None,
    ) -> JsonValue:
        return await self._runner.execute_tool(code, args, state, entrypoint=entrypoint)
