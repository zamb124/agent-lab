"""FastAPI dependencies для code-runner-csharp."""

from typing import Annotated

from fastapi import Depends

from apps.code_runner_csharp.container import (
    CodeRunnerCsharpContainer,
    get_code_runner_csharp_container,
)


def get_container() -> CodeRunnerCsharpContainer:
    return get_code_runner_csharp_container()


ContainerDep = Annotated[CodeRunnerCsharpContainer, Depends(get_container)]
