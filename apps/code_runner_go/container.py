"""DI контейнер code-runner-go."""

from __future__ import annotations

from apps.code_runner_go.config import get_code_runner_go_settings
from apps.code_runner_go.services.executor import GoSandboxExecutor
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class CodeRunnerGoContainer(BaseContainer):
    """Composition root Go sandbox runner."""

    @lazy
    def executor(self) -> GoSandboxExecutor:
        return GoSandboxExecutor()


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
