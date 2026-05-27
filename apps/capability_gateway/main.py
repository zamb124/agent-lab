"""FastAPI entrypoint capability-gateway."""

from apps.capability_gateway.api.v1.capabilities import router as capabilities_router
from apps.capability_gateway.config import (
    CapabilityGatewaySettings,
    get_capability_gateway_settings,
)
from apps.capability_gateway.container import get_capability_gateway_container
from core.app import create_service_app

app = create_service_app(
    service_name="capability_gateway",
    settings_class=CapabilityGatewaySettings,
    get_container=get_capability_gateway_container,
    routers=[capabilities_router],
    cors_origins=["*"],
    title="Platform Capability Gateway",
    description="Trusted gateway for sandbox platform capabilities",
    version="1.0.0",
    api_version="v1",
    include_auth_middleware=False,
    include_crud_routers=False,
    include_platform_routers=False,
    mount_repo_documentation=False,
    include_platform_pwa=False,
    documentation_gateway_prefix="capability-gateway",
)


if __name__ == "__main__":
    from core.app.server import serve

    serve(
        "capability_gateway",
        "apps.capability_gateway.main:app",
        get_capability_gateway_settings(),
    )
