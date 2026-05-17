"""DI контейнер code-runner-csharp."""

from __future__ import annotations

from apps.code_runner_csharp.config import get_code_runner_csharp_settings
from apps.code_runner_csharp.services.executor import CsharpSandboxExecutor
from core.container import BaseContainer, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class CodeRunnerCsharpContainer(BaseContainer):
    """Composition root C# sandbox runner."""

    @lazy
    def executor(self) -> CsharpSandboxExecutor:
        return CsharpSandboxExecutor()


_code_runner_csharp_container: CodeRunnerCsharpContainer | None = None


def get_code_runner_csharp_container() -> CodeRunnerCsharpContainer:
    global _code_runner_csharp_container
    if _code_runner_csharp_container is None:
        settings = get_code_runner_csharp_settings()
        _code_runner_csharp_container = CodeRunnerCsharpContainer(
            db_url=settings.database.shared_url,
            shared_db_url=settings.database.shared_url,
        )
        logger.info("CodeRunnerCsharpContainer инициализирован")
    return _code_runner_csharp_container


def reset_code_runner_csharp_container() -> None:
    global _code_runner_csharp_container
    _code_runner_csharp_container = None
