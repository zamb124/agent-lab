"""CodeRunnerClient — RemoteCodeRunner for trusted sandbox_codegen tool."""

from __future__ import annotations

from apps.flows.src.runners.remote import RemoteCodeRunner
from apps.flows.src.state import ExecutionState
from core.capabilities import CAPABILITY_LANGUAGE_SET
from core.types import JsonObject, JsonValue


class CodeRunnerClient:
    """Исполнение tool-кода в isolated code-runner-*."""

    _runner: RemoteCodeRunner

    def __init__(self, language: str = "python") -> None:
        if language not in CAPABILITY_LANGUAGE_SET:
            raise ValueError(f"Unsupported language: {language}")
        self._runner = RemoteCodeRunner(language)

    async def execute_tool(
        self,
        code: str,
        args: JsonObject,
        state: ExecutionState,
        *,
        entrypoint: str | None = None,
    ) -> JsonValue:
        return await self._runner.execute_tool(code, args, state, entrypoint=entrypoint)
