"""DI контейнер code-runner-node."""

from __future__ import annotations

from apps.code_runner_node.config import get_code_runner_node_settings
from apps.code_runner_node.services.executor import NodeSandboxExecutor
from core.container import BaseContainer, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class CodeRunnerNodeContainer(BaseContainer):
    """Composition root Node.js sandbox runner."""

    @lazy
    def executor(self) -> NodeSandboxExecutor:
        return NodeSandboxExecutor()


_code_runner_node_container: CodeRunnerNodeContainer | None = None


def get_code_runner_node_container() -> CodeRunnerNodeContainer:
    global _code_runner_node_container
    if _code_runner_node_container is None:
        settings = get_code_runner_node_settings()
        _code_runner_node_container = CodeRunnerNodeContainer(
            db_url=settings.database.shared_url,
            shared_db_url=settings.database.shared_url,
        )
        logger.info("CodeRunnerNodeContainer инициализирован")
    return _code_runner_node_container


def reset_code_runner_node_container() -> None:
    global _code_runner_node_container
    _code_runner_node_container = None
