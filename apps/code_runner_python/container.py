"""DI контейнер code-runner-python."""

from __future__ import annotations

from apps.code_runner_python.config import get_code_runner_python_settings
from apps.code_runner_python.services.executor import PythonSandboxExecutor
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class CodeRunnerPythonContainer(BaseContainer):
    """Composition root Python sandbox runner."""

    @lazy
    def executor(self) -> PythonSandboxExecutor:
        return PythonSandboxExecutor()


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
