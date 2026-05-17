"""FastAPI dependencies для code-runner-node."""

from typing import Annotated

from fastapi import Depends

from apps.code_runner_node.container import (
    CodeRunnerNodeContainer,
    get_code_runner_node_container,
)


def get_container() -> CodeRunnerNodeContainer:
    return get_code_runner_node_container()


ContainerDep = Annotated[CodeRunnerNodeContainer, Depends(get_container)]
