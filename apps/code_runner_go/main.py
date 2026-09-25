"""FastAPI entrypoint code-runner-go."""

from apps.code_runner_go.api.v1.analyze import router as analyze_router
from apps.code_runner_go.api.v1.execute import router as execute_router
from apps.code_runner_go.api.v1.lsp import router as lsp_router
from apps.code_runner_go.api.v1.validate import router as validate_router
from apps.code_runner_go.config import CodeRunnerGoSettings, get_code_runner_go_settings
from apps.code_runner_go.di import CodeRunnerGoDi
from core.app import create_service_app

app = create_service_app(
    "code_runner_go",
    CodeRunnerGoSettings,
    CodeRunnerGoDi,
    database="shared_url",
    routers=[execute_router, validate_router, analyze_router, lsp_router],
    cors_origins=["*"],
    title="Platform Go Code Runner",
    description="Untrusted Go sandbox runner",
    version="1.0.0",
    api_version="v1",
    include_auth_middleware=False,
    include_tracing_lifecycle=True,
    include_platform_lifecycle=False,
    include_platform_routers=False,
    mount_repo_documentation=False,
    include_platform_pwa=False,
    documentation_gateway_prefix="code-runner-go",
)


if __name__ == "__main__":
    from core.app.server import serve

    serve(
        "code_runner_go",
        "apps.code_runner_go.main:app",
        get_code_runner_go_settings(),
    )
