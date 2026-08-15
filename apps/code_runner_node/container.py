"""DI контейнер code-runner-node."""

from __future__ import annotations

from apps.code_runner_node.config import get_code_runner_node_settings
from apps.code_runner_node.services.executor import NodeSandboxExecutor
from apps.code_runner_node.services.lsp import node_lsp_command, prepare_node_lsp_workspace
from core.capabilities.lsp_session import LspSessionManager
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class CodeRunnerNodeContainer(BaseContainer):
    """Composition root Node.js sandbox runner."""

    @lazy
    def executor(self) -> NodeSandboxExecutor:
        return NodeSandboxExecutor()

    @lazy
    def lsp_manager(self) -> LspSessionManager:
        return LspSessionManager(
            command_factory=node_lsp_command,
            extra_prepare=prepare_node_lsp_workspace,
            public_ws_prefix="/code-runner-node/api/v1/lsp/ws",
        )


def _create_code_runner_node_container() -> CodeRunnerNodeContainer:
    settings = get_code_runner_node_settings()
    return CodeRunnerNodeContainer(
        db_url=settings.database.shared_url,
        shared_db_url=settings.database.shared_url,
    )


_code_runner_node_registry: ContainerRegistry[CodeRunnerNodeContainer] = ContainerRegistry(
    _create_code_runner_node_container, name="CodeRunnerNodeContainer"
)

get_code_runner_node_container = _code_runner_node_registry.get
reset_code_runner_node_container = _code_runner_node_registry.reset
