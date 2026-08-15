"""DI контейнер code-runner-go."""

from __future__ import annotations

from apps.code_runner_go.config import get_code_runner_go_settings
from apps.code_runner_go.services.executor import GoSandboxExecutor
from apps.code_runner_go.services.lsp import go_lsp_command, prepare_go_lsp_workspace
from core.capabilities.lsp_session import LspSessionManager
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class CodeRunnerGoContainer(BaseContainer):
    """Composition root Go sandbox runner."""

    @lazy
    def executor(self) -> GoSandboxExecutor:
        return GoSandboxExecutor()

    @lazy
    def lsp_manager(self) -> LspSessionManager:
        return LspSessionManager(
            command_factory=go_lsp_command,
            extra_prepare=prepare_go_lsp_workspace,
            extra_env={"GOPROXY": "off", "GO111MODULE": "on"},
            public_ws_prefix="/code-runner-go/api/v1/lsp/ws",
        )


def _create_code_runner_go_container() -> CodeRunnerGoContainer:
    settings = get_code_runner_go_settings()
    return CodeRunnerGoContainer(
        db_url=settings.database.shared_url,
        shared_db_url=settings.database.shared_url,
    )


_code_runner_go_registry: ContainerRegistry[CodeRunnerGoContainer] = ContainerRegistry(
    _create_code_runner_go_container, name="CodeRunnerGoContainer"
)

get_code_runner_go_container = _code_runner_go_registry.get
reset_code_runner_go_container = _code_runner_go_registry.reset
