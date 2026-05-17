"""FastAPI entrypoint code-runner-csharp."""

from apps.code_runner_csharp.api.v1.execute import router as execute_router
from apps.code_runner_csharp.config import (
    CodeRunnerCsharpSettings,
    get_code_runner_csharp_settings,
)
from apps.code_runner_csharp.container import get_code_runner_csharp_container
from core.app import create_service_app

app = create_service_app(
    service_name="code_runner_csharp",
    settings_class=CodeRunnerCsharpSettings,
    get_container=get_code_runner_csharp_container,
    routers=[execute_router],
    repository_names=[],
    cors_origins=["*"],
    title="Platform C# Code Runner",
    description="Untrusted C# sandbox runner",
    version="1.0.0",
    api_version="v1",
    include_auth_middleware=False,
    include_crud_routers=False,
    include_tracing_lifecycle=True,
    include_platform_lifecycle=False,
    include_platform_routers=False,
    mount_repo_documentation=False,
    include_platform_pwa=False,
    documentation_gateway_prefix="code-runner-csharp",
)


if __name__ == "__main__":
    import uvicorn

    settings = get_code_runner_csharp_settings()
    uvicorn.run(
        "apps.code_runner_csharp.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
