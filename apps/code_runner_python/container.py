"""DI контейнер code-runner-python."""

from __future__ import annotations

from apps.code_runner_python.config import get_code_runner_python_settings
from apps.code_runner_python.services.executor import PythonSandboxExecutor
from apps.code_runner_python.services.lsp import prepare_python_lsp_workspace, python_lsp_command
from core.capabilities.lsp_session import LspSessionManager
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class CodeRunnerPythonContainer(BaseContainer):
    """Composition root Python sandbox runner."""

    @lazy
    def executor(self) -> PythonSandboxExecutor:
        return PythonSandboxExecutor()

    @lazy
    def lsp_manager(self) -> LspSessionManager:
        return LspSessionManager(
            command_factory=python_lsp_command,
            extra_prepare=prepare_python_lsp_workspace,
            public_ws_prefix="/code-runner-python/api/v1/lsp/ws",
        )


def _create_code_runner_python_container() -> CodeRunnerPythonContainer:
    settings = get_code_runner_python_settings()
    return CodeRunnerPythonContainer(
        db_url=settings.database.shared_url,
        shared_db_url=settings.database.shared_url,
    )


_code_runner_python_registry: ContainerRegistry[CodeRunnerPythonContainer] = ContainerRegistry(
    _create_code_runner_python_container, name="CodeRunnerPythonContainer"
)

get_code_runner_python_container = _code_runner_python_registry.get
reset_code_runner_python_container = _code_runner_python_registry.reset
