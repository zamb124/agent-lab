"""FastAPI entrypoint code-runner-python."""

from apps.code_runner_python.api.v1.execute import router as execute_router
from apps.code_runner_python.api.v1.validate import router as validate_router
from apps.code_runner_python.config import (
    CodeRunnerPythonSettings,
    get_code_runner_python_settings,
)
from apps.code_runner_python.container import get_code_runner_python_container
from core.app import create_service_app

app = create_service_app(
    service_name="code_runner_python",
    settings_class=CodeRunnerPythonSettings,
    get_container=get_code_runner_python_container,
    routers=[execute_router, validate_router],
    repository_names=[],
    cors_origins=["*"],
    title="Platform Python Code Runner",
    description="Untrusted Python sandbox runner",
    version="1.0.0",
    api_version="v1",
    include_auth_middleware=False,
    include_crud_routers=False,
    include_tracing_lifecycle=True,
    include_platform_lifecycle=False,
    include_platform_routers=False,
    mount_repo_documentation=False,
    include_platform_pwa=False,
    documentation_gateway_prefix="code-runner-python",
)


if __name__ == "__main__":
    import uvicorn

    settings = get_code_runner_python_settings()
    uvicorn.run(
        "apps.code_runner_python.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
