"""DI процесса code_runner_go: sandbox Go."""

from collections.abc import AsyncIterator
from typing import Annotated

from apps.code_runner_go.services.executor import GoSandboxExecutor
from apps.code_runner_go.services.lsp import go_lsp_command, prepare_go_lsp_workspace
from core.capabilities.lsp_session import LspSessionManager
from core.di import ServiceDi, http_di, recipe, task_di


@recipe
async def lsp_manager() -> AsyncIterator[LspSessionManager]:
    manager = LspSessionManager(
        command_factory=go_lsp_command,
        extra_prepare=prepare_go_lsp_workspace,
        extra_env={"GOPROXY": "off", "GO111MODULE": "on"},
        public_ws_prefix="/code-runner-go/api/v1/lsp/ws",
    )
    yield manager
    await manager.aclose()


class CodeRunnerGoDi(ServiceDi, recipes=(lsp_manager,)):
    executor: GoSandboxExecutor
    lsp_manager: LspSessionManager


Di = Annotated[CodeRunnerGoDi, http_di(CodeRunnerGoDi), task_di(CodeRunnerGoDi)]
