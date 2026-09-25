"""DI процесса code_runner_csharp: sandbox C#."""

from collections.abc import AsyncIterator
from typing import Annotated

from apps.code_runner_csharp.services.executor import CsharpSandboxExecutor
from apps.code_runner_csharp.services.lsp import csharp_lsp_command, prepare_csharp_lsp_workspace
from core.capabilities.lsp_session import LspSessionManager
from core.di import ServiceDi, http_di, recipe, task_di


@recipe
async def lsp_manager() -> AsyncIterator[LspSessionManager]:
    manager = LspSessionManager(
        command_factory=csharp_lsp_command,
        extra_prepare=prepare_csharp_lsp_workspace,
        public_ws_prefix="/code-runner-csharp/api/v1/lsp/ws",
    )
    yield manager
    await manager.aclose()


class CodeRunnerCsharpDi(ServiceDi, recipes=(lsp_manager,)):
    executor: CsharpSandboxExecutor
    lsp_manager: LspSessionManager


Di = Annotated[CodeRunnerCsharpDi, http_di(CodeRunnerCsharpDi), task_di(CodeRunnerCsharpDi)]
