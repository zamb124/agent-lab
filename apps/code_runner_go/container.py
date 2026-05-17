"""DI контейнер code-runner-go."""

from __future__ import annotations

from apps.code_runner_go.config import get_code_runner_go_settings
from apps.code_runner_go.services.executor import GoSandboxExecutor
from core.container import BaseContainer, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class CodeRunnerGoContainer(BaseContainer):
    """Composition root Go sandbox runner."""

    @lazy
    def executor(self) -> GoSandboxExecutor:
        return GoSandboxExecutor()


_code_runner_go_container: CodeRunnerGoContainer | None = None


def get_code_runner_go_container() -> CodeRunnerGoContainer:
    global _code_runner_go_container
    if _code_runner_go_container is None:
        settings = get_code_runner_go_settings()
        _code_runner_go_container = CodeRunnerGoContainer(
            db_url=settings.database.shared_url,
            shared_db_url=settings.database.shared_url,
        )
        logger.info("CodeRunnerGoContainer инициализирован")
    return _code_runner_go_container


def reset_code_runner_go_container() -> None:
    global _code_runner_go_container
    _code_runner_go_container = None
