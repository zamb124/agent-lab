"""DI процесса code_runner_python: sandbox Python."""

from collections.abc import AsyncIterator
from typing import Annotated

from apps.code_runner_python.services.executor import PythonSandboxExecutor
from apps.code_runner_python.services.lsp import prepare_python_lsp_workspace, python_lsp_command
from core.capabilities.lsp_session import LspSessionManager
from core.di import ServiceDi, http_di, recipe, task_di


@recipe
async def executor() -> AsyncIterator[PythonSandboxExecutor]:
    sandbox = PythonSandboxExecutor()
    yield sandbox
    await sandbox.aclose()


@recipe
async def lsp_manager() -> AsyncIterator[LspSessionManager]:
    manager = LspSessionManager(
        command_factory=python_lsp_command,
        extra_prepare=prepare_python_lsp_workspace,
        public_ws_prefix="/code-runner-python/api/v1/lsp/ws",
    )
    yield manager
    await manager.aclose()


class CodeRunnerPythonDi(ServiceDi, recipes=(executor, lsp_manager)):
    executor: PythonSandboxExecutor
    lsp_manager: LspSessionManager


Di = Annotated[CodeRunnerPythonDi, http_di(CodeRunnerPythonDi), task_di(CodeRunnerPythonDi)]
