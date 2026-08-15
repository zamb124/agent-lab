"""FastAPI entrypoint code-runner-csharp."""

from fastapi import FastAPI

from apps.code_runner_csharp.api.v1.analyze import router as analyze_router
from apps.code_runner_csharp.api.v1.execute import router as execute_router
from apps.code_runner_csharp.api.v1.lsp import router as lsp_router
from apps.code_runner_csharp.api.v1.validate import router as validate_router
from apps.code_runner_csharp.config import (
    CodeRunnerCsharpSettings,
    get_code_runner_csharp_settings,
)
from apps.code_runner_csharp.container import (
    CodeRunnerCsharpContainer,
    get_code_runner_csharp_container,
)
from core.app import create_service_app


async def on_shutdown(_app: FastAPI, container: CodeRunnerCsharpContainer) -> None:
    if "_cached_lsp_manager" in container.__dict__:
        await container.lsp_manager.aclose()


app = create_service_app(
    service_name="code_runner_csharp",
    settings_class=CodeRunnerCsharpSettings,
    get_container=get_code_runner_csharp_container,
    routers=[execute_router, validate_router, analyze_router, lsp_router],
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
    on_shutdown=on_shutdown,
)


if __name__ == "__main__":
    from core.app.server import serve

    serve(
        "code_runner_csharp",
        "apps.code_runner_csharp.main:app",
        get_code_runner_csharp_settings(),
    )
