"""FastAPI dependencies для code-runner-go."""

from typing import Annotated

from fastapi import Depends

from apps.code_runner_go.container import CodeRunnerGoContainer, get_code_runner_go_container


def get_container() -> CodeRunnerGoContainer:
    return get_code_runner_go_container()


ContainerDep = Annotated[CodeRunnerGoContainer, Depends(get_container)]
