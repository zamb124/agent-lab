"""DI контейнер code-runner-python."""

from __future__ import annotations

from apps.code_runner_python.config import get_code_runner_python_settings
from apps.code_runner_python.services.executor import PythonSandboxExecutor
from core.container import BaseContainer, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class CodeRunnerPythonContainer(BaseContainer):
    """Composition root Python sandbox runner."""

    @lazy
    def executor(self) -> PythonSandboxExecutor:
        return PythonSandboxExecutor()


_code_runner_python_container: CodeRunnerPythonContainer | None = None


def get_code_runner_python_container() -> CodeRunnerPythonContainer:
    global _code_runner_python_container
    if _code_runner_python_container is None:
        settings = get_code_runner_python_settings()
        _code_runner_python_container = CodeRunnerPythonContainer(
            db_url=settings.database.shared_url,
            shared_db_url=settings.database.shared_url,
        )
        logger.info("CodeRunnerPythonContainer инициализирован")
    return _code_runner_python_container


def reset_code_runner_python_container() -> None:
    global _code_runner_python_container
    _code_runner_python_container = None
