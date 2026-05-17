"""FastAPI dependencies для code-runner-python."""

from typing import Annotated

from fastapi import Depends

from apps.code_runner_python.container import (
    CodeRunnerPythonContainer,
    get_code_runner_python_container,
)


def get_container() -> CodeRunnerPythonContainer:
    return get_code_runner_python_container()


ContainerDep = Annotated[CodeRunnerPythonContainer, Depends(get_container)]
