"""DI процесса code_runner_node: sandbox JavaScript и TypeScript."""

from collections.abc import AsyncIterator
from typing import Annotated

from apps.code_runner_node.services.executor import NodeSandboxExecutor
from apps.code_runner_node.services.lsp import node_lsp_command, prepare_node_lsp_workspace
from core.capabilities.lsp_session import LspSessionManager
from core.di import ServiceDi, http_di, recipe, task_di


@recipe
async def lsp_manager() -> AsyncIterator[LspSessionManager]:
    manager = LspSessionManager(
        command_factory=node_lsp_command,
        extra_prepare=prepare_node_lsp_workspace,
        public_ws_prefix="/code-runner-node/api/v1/lsp/ws",
    )
    yield manager
    await manager.aclose()


class CodeRunnerNodeDi(ServiceDi, recipes=(lsp_manager,)):
    executor: NodeSandboxExecutor
    lsp_manager: LspSessionManager


Di = Annotated[CodeRunnerNodeDi, http_di(CodeRunnerNodeDi), task_di(CodeRunnerNodeDi)]
