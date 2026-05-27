"""FastAPI entrypoint code-runner-node."""

from apps.code_runner_node.api.v1.execute import router as execute_router
from apps.code_runner_node.api.v1.validate import router as validate_router
from apps.code_runner_node.config import CodeRunnerNodeSettings, get_code_runner_node_settings
from apps.code_runner_node.container import get_code_runner_node_container
from core.app import create_service_app

app = create_service_app(
    service_name="code_runner_node",
    settings_class=CodeRunnerNodeSettings,
    get_container=get_code_runner_node_container,
    routers=[execute_router, validate_router],
    cors_origins=["*"],
    title="Platform Node Code Runner",
    description="Untrusted JavaScript/TypeScript sandbox runner",
    version="1.0.0",
    api_version="v1",
    include_auth_middleware=False,
    include_crud_routers=False,
    include_tracing_lifecycle=True,
    include_platform_lifecycle=False,
    include_platform_routers=False,
    mount_repo_documentation=False,
    include_platform_pwa=False,
    documentation_gateway_prefix="code-runner-node",
)


if __name__ == "__main__":
    from core.app.server import serve

    serve(
        "code_runner_node",
        "apps.code_runner_node.main:app",
        get_code_runner_node_settings(),
    )
