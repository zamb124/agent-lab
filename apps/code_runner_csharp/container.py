"""DI контейнер code-runner-csharp."""

from __future__ import annotations

from apps.code_runner_csharp.config import get_code_runner_csharp_settings
from apps.code_runner_csharp.services.executor import CsharpSandboxExecutor
from apps.code_runner_csharp.services.lsp import csharp_lsp_command, prepare_csharp_lsp_workspace
from core.capabilities.lsp_session import LspSessionManager
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class CodeRunnerCsharpContainer(BaseContainer):
    """Composition root C# sandbox runner."""

    @lazy
    def executor(self) -> CsharpSandboxExecutor:
        return CsharpSandboxExecutor()

    @lazy
    def lsp_manager(self) -> LspSessionManager:
        return LspSessionManager(
            command_factory=csharp_lsp_command,
            extra_prepare=prepare_csharp_lsp_workspace,
            public_ws_prefix="/code-runner-csharp/api/v1/lsp/ws",
        )


def _create_code_runner_csharp_container() -> CodeRunnerCsharpContainer:
    settings = get_code_runner_csharp_settings()
    return CodeRunnerCsharpContainer(
        db_url=settings.database.shared_url,
        shared_db_url=settings.database.shared_url,
    )


_code_runner_csharp_registry: ContainerRegistry[CodeRunnerCsharpContainer] = ContainerRegistry(
    _create_code_runner_csharp_container, name="CodeRunnerCsharpContainer"
)

get_code_runner_csharp_container = _code_runner_csharp_registry.get
reset_code_runner_csharp_container = _code_runner_csharp_registry.reset
