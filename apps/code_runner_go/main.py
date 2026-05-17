"""FastAPI entrypoint code-runner-go."""

from apps.code_runner_go.api.v1.execute import router as execute_router
from apps.code_runner_go.config import CodeRunnerGoSettings, get_code_runner_go_settings
from apps.code_runner_go.container import get_code_runner_go_container
from core.app import create_service_app

app = create_service_app(
    service_name="code_runner_go",
    settings_class=CodeRunnerGoSettings,
    get_container=get_code_runner_go_container,
    routers=[execute_router],
    repository_names=[],
    cors_origins=["*"],
    title="Platform Go Code Runner",
    description="Untrusted Go sandbox runner",
    version="1.0.0",
    api_version="v1",
    include_auth_middleware=False,
    include_crud_routers=False,
    include_tracing_lifecycle=True,
    include_platform_lifecycle=False,
    include_platform_routers=False,
    mount_repo_documentation=False,
    include_platform_pwa=False,
    documentation_gateway_prefix="code-runner-go",
)


if __name__ == "__main__":
    import uvicorn

    settings = get_code_runner_go_settings()
    uvicorn.run(
        "apps.code_runner_go.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
