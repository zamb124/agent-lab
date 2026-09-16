"""HTTP client for guest_runtime farm on top of ServiceClient."""

from __future__ import annotations

from typing import NoReturn

from core.clients.service_client import ServiceClient, ServiceClientError
from core.config import get_settings
from core.guest_runtime.models import (
    GuestBuildBusyError,
    GuestEnsureLeaseRequest,
    GuestEnsureLeaseResponse,
    GuestLeaseCapError,
    GuestRebuildRequest,
    GuestRebuildResponse,
    GuestRuntimeLogsResponse,
    GuestRuntimeStatusResponse,
)
from core.types import require_json_object

_API = "/guest-runtime/api/v1"


def _reraise_farm_error(exc: ServiceClientError) -> NoReturn:
    text = exc.response_text if exc.response_text is not None else str(exc)
    if exc.status_code == 409:
        if "cap" in text:
            raise GuestLeaseCapError(text) from exc
        raise GuestBuildBusyError(text) from exc
    if exc.status_code == 400:
        raise ValueError(text) from exc
    if exc.status_code == 404:
        raise LookupError(text) from exc
    raise exc


class GuestRuntimeClient:
    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._http: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )

    def a2a_url(self, flow_id: str, node_id: str) -> str:
        base = get_settings().server.get_service_url("guest_runtime").rstrip("/")
        return f"{base}{_API}/a2a/{flow_id}/{node_id}"

    async def rebuild(self, body: GuestRebuildRequest) -> GuestRebuildResponse:
        try:
            raw = await self._http.post(
                "guest_runtime",
                f"{_API}/rebuild",
                json=body.model_dump(mode="json"),
                timeout=600.0,
            )
        except ServiceClientError as exc:
            _reraise_farm_error(exc)
        return GuestRebuildResponse.model_validate(require_json_object(raw, "guest.rebuild"))

    async def ensure_lease(self, body: GuestEnsureLeaseRequest) -> GuestEnsureLeaseResponse:
        try:
            raw = await self._http.post(
                "guest_runtime",
                f"{_API}/leases/ensure",
                json=body.model_dump(mode="json"),
                timeout=600.0,
            )
        except ServiceClientError as exc:
            _reraise_farm_error(exc)
        return GuestEnsureLeaseResponse.model_validate(
            require_json_object(raw, "guest.ensure_lease")
        )

    async def status(self, flow_id: str, node_id: str) -> GuestRuntimeStatusResponse:
        raw = await self._http.get(
            "guest_runtime",
            f"{_API}/runtimes/{flow_id}/{node_id}",
            timeout=30.0,
        )
        return GuestRuntimeStatusResponse.model_validate(
            require_json_object(raw, "guest.status")
        )

    async def logs(
        self,
        flow_id: str,
        node_id: str,
        *,
        task_id: str | None = None,
        session_id: str | None = None,
        context_id: str | None = None,
    ) -> GuestRuntimeLogsResponse:
        params: dict[str, str] = {}
        if task_id is not None:
            if task_id.strip() == "":
                raise ValueError("task_id must be non-empty when provided")
            params["task_id"] = task_id
        if session_id is not None:
            if session_id.strip() == "":
                raise ValueError("session_id must be non-empty when provided")
            params["session_id"] = session_id
        if context_id is not None:
            if context_id.strip() == "":
                raise ValueError("context_id must be non-empty when provided")
            params["context_id"] = context_id
        raw = await self._http.get(
            "guest_runtime",
            f"{_API}/runtimes/{flow_id}/{node_id}/logs",
            timeout=30.0,
            params=params if params else None,
        )
        return GuestRuntimeLogsResponse.model_validate(
            require_json_object(raw, "guest.logs")
        )

    async def drop(self, flow_id: str, node_id: str) -> None:
        _ = await self._http.delete(
            "guest_runtime",
            f"{_API}/runtimes/{flow_id}/{node_id}",
            timeout=60.0,
        )
