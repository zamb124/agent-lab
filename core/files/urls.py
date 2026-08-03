"""Публичные URL Files API: каждый сервис самодостаточен, без frontend-канона."""

from __future__ import annotations

from contextvars import ContextVar

# HTTP public path segment (ingress) для service_name процесса.
_LITSERVE_PROCESS_NAME = "provider" + "_litserve"
_SERVICE_TO_FILES_ROUTE_SEGMENT: dict[str, str] = {
    "office": "documents",
    _LITSERVE_PROCESS_NAME: "litserve",
    "capability_gateway": "capability-gateway",
    "code_runner_python": "code-runner-python",
    "code_runner_node": "code-runner-node",
    "code_runner_go": "code-runner-go",
    "code_runner_csharp": "code-runner-csharp",
    "flows_worker": "flows",
    "crm_worker": "crm",
    "rag_worker": "rag",
    "sync_worker": "sync",
    "search_worker": "search",
    "idle_worker": "frontend",
}

_files_route_segment: ContextVar[str | None] = ContextVar(
    "files_route_segment",
    default=None,
)


def normalize_files_route_segment(service_or_segment: str) -> str:
    raw = service_or_segment.strip().strip("/")
    if raw == "":
        raise ValueError("files route segment is required")
    mapped = _SERVICE_TO_FILES_ROUTE_SEGMENT.get(raw)
    if mapped is not None:
        return mapped
    return raw


def resolve_files_route_segment(
    service_name: str,
    *,
    documentation_gateway_prefix: str | None = None,
) -> str:
    if documentation_gateway_prefix is not None and documentation_gateway_prefix.strip() != "":
        return normalize_files_route_segment(documentation_gateway_prefix)
    return normalize_files_route_segment(service_name)


def set_files_route_segment(route_segment: str) -> None:
    _ = _files_route_segment.set(normalize_files_route_segment(route_segment))


def get_files_route_segment() -> str | None:
    value = _files_route_segment.get()
    if value is None:
        return None
    if value.strip() == "":
        raise RuntimeError("files route segment ContextVar is empty")
    return value


def require_files_route_segment() -> str:
    value = get_files_route_segment()
    if value is None:
        raise RuntimeError(
            "files route segment is not configured; call set_files_route_segment "
            + "from create_service_app / worker bootstrap"
        )
    return value


def files_api_prefix(route_segment: str | None = None) -> str:
    segment = (
        normalize_files_route_segment(route_segment)
        if route_segment is not None
        else require_files_route_segment()
    )
    return f"/{segment}/api/v1/files"


def files_download_url(file_id: str, *, route_segment: str | None = None) -> str:
    if file_id.strip() == "":
        raise ValueError("file_id is required")
    return f"{files_api_prefix(route_segment)}/download/{file_id}"


__all__ = [
    "files_api_prefix",
    "files_download_url",
    "get_files_route_segment",
    "normalize_files_route_segment",
    "require_files_route_segment",
    "resolve_files_route_segment",
    "set_files_route_segment",
]
