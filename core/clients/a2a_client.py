"""A2A Client — HTTP client for external agents (A2A Protocol 1.0 JSON-RPC)."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Sequence
from typing import cast

import httpx
from pydantic import Field

from core.a2a.extensions import (
    A2A_EXTENSIONS_HEADER,
    A2UI_EXTENSION_URI,
    A2UI_MIME_TYPE,
    parse_a2a_extensions_header,
)
from core.a2a.methods import GET_TASK, SEND_MESSAGE
from core.a2a.task_json import extract_text_from_parts_json, extract_text_from_task_json
from core.a2a.task_states import wire_task_state_to_platform
from core.context import get_context
from core.http import get_httpx_client
from core.internal_context_headers import build_internal_context_headers
from core.logging import get_logger
from core.models import StrictBaseModel
from core.test_scope import TEST_SCOPE_HEADER, resolve_test_scope
from core.types import JsonObject, parse_json_object, require_json_object

logger = get_logger(__name__)

A2A_PROTOCOL_VERSION = "1.0"
A2A_VERSION_HEADER = "A2A-Version"
_SEND_TASK_OPEN_STATES = frozenset({"submitted", "working"})
_SEND_TASK_ENQUEUE_HTTP_TIMEOUT_SECONDS = 30.0
_SEND_TASK_POLL_INTERVAL_SECONDS = 0.3


class A2ATaskResult(StrictBaseModel):
    """Structured SendMessage result: exact Task JSON plus derived text convenience."""

    task: JsonObject = Field(..., description="Exact A2A Task ProtoJSON from result")
    artifacts: list[JsonObject] = Field(
        ...,
        description="Lossless Task.artifacts list (artifactId required per item)",
    )
    status: str = Field(..., description="Platform kebab task status (from TASK_STATE_*)")
    response: str = Field(..., description="Derived text convenience from Task/history/artifacts")
    raw: JsonObject = Field(..., description="Full JSON-RPC response envelope")
    negotiated_extensions: list[str] = Field(
        default_factory=list,
        description="Activated extension URIs for this Task",
    )


class A2AClientError(Exception):
    """A2A client protocol or transport error."""


def _extract_task_status_message(status_obj: JsonObject) -> str | None:
    message_value = status_obj.get("message")
    if not isinstance(message_value, dict):
        return None
    message = require_json_object(message_value, "A2A result.status.message")
    return extract_text_from_parts_json(message.get("parts"))


def _unwrap_send_message_task(result_payload: JsonObject) -> JsonObject:
    """SendMessageResponse ProtoJSON oneof: `task` | `message`.

    Official a2a-sdk wraps Task as `result.task`. Platform channel may still
    return a bare Task ProtoJSON at `result` (status/artifacts at top level).
    """
    if "status" in result_payload or "artifacts" in result_payload or "history" in result_payload:
        return result_payload
    task_value = result_payload.get("task")
    if isinstance(task_value, dict):
        return require_json_object(task_value, "A2A result.task")
    message_value = result_payload.get("message")
    if isinstance(message_value, dict):
        raise A2AClientError(
            "A2A SendMessage returned Message payload; Task is required for this client"
        )
    raise A2AClientError("A2A response missing result.task / Task fields")


def _require_artifacts(task_result: JsonObject) -> list[JsonObject]:
    artifacts_raw = task_result.get("artifacts")
    if artifacts_raw is None:
        return []
    if not isinstance(artifacts_raw, list):
        raise A2AClientError("A2A result.artifacts must be a list")
    artifacts: list[JsonObject] = []
    for index, item in enumerate(artifacts_raw):
        artifact = require_json_object(item, f"A2A result.artifacts[{index}]")
        artifact_id = artifact.get("artifactId")
        if not isinstance(artifact_id, str) or artifact_id.strip() == "":
            raise A2AClientError(
                f"A2A result.artifacts[{index}].artifactId is required"
            )
        artifacts.append(artifact)
    return artifacts


def _negotiated_extensions_from_task(task_result: JsonObject) -> list[str]:
    metadata_raw = task_result.get("metadata")
    if not isinstance(metadata_raw, dict):
        return []
    metadata = require_json_object(metadata_raw, "A2A result.metadata")
    platform_ui_raw = metadata.get("platformUi")
    if not isinstance(platform_ui_raw, dict):
        return []
    platform_ui = require_json_object(platform_ui_raw, "A2A result.metadata.platformUi")
    extensions_raw = platform_ui.get("negotiated_extensions")
    if extensions_raw is None:
        return []
    if not isinstance(extensions_raw, list):
        raise A2AClientError(
            "A2A result.metadata.platformUi.negotiated_extensions must be strings"
        )
    negotiated: list[str] = []
    for item in extensions_raw:
        if not isinstance(item, str) or item.strip() == "":
            raise A2AClientError(
                "A2A result.metadata.platformUi.negotiated_extensions must be strings"
            )
        negotiated.append(item.strip())
    return negotiated


def _agent_card_supports_a2ui(agent_card: JsonObject) -> bool:
    capabilities_raw = agent_card.get("capabilities")
    if isinstance(capabilities_raw, dict):
        capabilities = require_json_object(capabilities_raw, "AgentCard.capabilities")
        extensions_raw = capabilities.get("extensions")
        if isinstance(extensions_raw, list):
            for item in extensions_raw:
                if isinstance(item, str) and item.strip() == A2UI_EXTENSION_URI:
                    return True
                if isinstance(item, dict):
                    uri = item.get("uri") or item.get("id")
                    if isinstance(uri, str) and uri.strip() == A2UI_EXTENSION_URI:
                        return True
    extensions_top = agent_card.get("extensions")
    if isinstance(extensions_top, list):
        for item in extensions_top:
            if isinstance(item, str) and item.strip() == A2UI_EXTENSION_URI:
                return True
    return False


def _task_id_from_result(task_result: JsonObject) -> str:
    task_id = task_result.get("id")
    if not isinstance(task_id, str) or task_id.strip() == "":
        raise A2AClientError("A2A Task.id is required")
    return task_id


class A2AClient:
    """HTTP client for A2A Protocol 1.0 SendMessage / AgentCard."""

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout: float = timeout

    async def get_agent_card(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
    ) -> JsonObject:
        url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
        merged_headers = dict(headers or {})
        try:
            async with get_httpx_client(timeout=self.timeout) as client:
                response = await client.get(url, headers=merged_headers)
                if response.status_code != 200:
                    raise A2AClientError(
                        f"Failed to get agent-card from {url}: {response.status_code}"
                    )
                return parse_json_object(response.content, "A2A agent-card")
        except httpx.HTTPError as exc:
            raise A2AClientError(f"HTTP error getting agent card from {url}: {exc}") from exc
        except ValueError as exc:
            raise A2AClientError(f"Invalid JSON response from {url}: {exc}") from exc

    async def send_message(
        self,
        base_url: str,
        *,
        parts: Sequence[JsonObject],
        context_id: str,
        message_id: str | None = None,
        role: str = "ROLE_USER",
        metadata: JsonObject | None = None,
        headers: dict[str, str] | None = None,
        accepted_output_modes: Sequence[str] | None = None,
        activated_extensions: Sequence[str] = (),
        timeout: float | None = None,
        return_immediately: bool = False,
    ) -> A2ATaskResult:
        """Send a structured A2A Message (Parts preserved, no text collapse on wire)."""
        if not parts:
            raise A2AClientError("SendMessage parts must be non-empty")
        for index, part in enumerate(parts):
            _ = require_json_object(part, f"SendMessage.parts[{index}]")

        message_payload: JsonObject = {
            "role": role,
            "parts": list(parts),
            "messageId": message_id or str(uuid.uuid4()),
            "contextId": context_id,
        }
        modes = (
            list(accepted_output_modes)
            if accepted_output_modes is not None
            else ["text", "application/json", A2UI_MIME_TYPE, "*/*"]
        )
        params_payload: JsonObject = {
            "message": message_payload,
            "configuration": {
                "acceptedOutputModes": modes,
                "returnImmediately": return_immediately,
            },
        }
        if metadata:
            params_payload["metadata"] = dict(metadata)

        return await self._post_rpc(
            base_url,
            method=SEND_MESSAGE,
            params=params_payload,
            headers=headers,
            activated_extensions=activated_extensions,
            timeout=timeout,
            rpc_label="SendMessage",
        )

    async def send_task(
        self,
        base_url: str,
        content: str,
        session_id: str | None = None,
        branch_id: str = "default",
        metadata: JsonObject | None = None,
        headers: dict[str, str] | None = None,
        *,
        timeout: float | None = None,
        negotiate_extensions: bool = False,
    ) -> A2ATaskResult:
        """Convenience SendMessage with a single text Part.

        Internal callers (CRM skills, remote_flow) do not hold the peer HTTP
        worker for the graph: SendMessageConfiguration.returnImmediately=true,
        then GetTask until terminal/interrupted or timeout. A2UI negotiation
        is opt-in. Pass negotiate_extensions=True for Flow UI hosts.
        """
        context_id = session_id or str(uuid.uuid4())
        final_metadata: JsonObject = dict(metadata) if metadata is not None else {}
        if branch_id and branch_id != "default":
            final_metadata["branch"] = branch_id

        activated: list[str] = []
        accepted_modes: list[str] = ["text", "application/json", "*/*"]
        if negotiate_extensions:
            try:
                agent_card = await self.get_agent_card(base_url, headers=headers)
            except A2AClientError:
                agent_card = None
            if agent_card is not None and _agent_card_supports_a2ui(agent_card):
                activated.append(A2UI_EXTENSION_URI)
                accepted_modes.append(A2UI_MIME_TYPE)

        logger.debug(f"A2A send_task to {base_url}: {content[:100]}...")
        overall_timeout = self.timeout if timeout is None else timeout
        enqueue_timeout = min(_SEND_TASK_ENQUEUE_HTTP_TIMEOUT_SECONDS, overall_timeout)
        submitted = await self.send_message(
            base_url,
            parts=[{"text": content}],
            context_id=context_id,
            metadata=final_metadata or None,
            headers=headers,
            accepted_output_modes=accepted_modes,
            activated_extensions=activated,
            timeout=enqueue_timeout,
            return_immediately=True,
        )
        if submitted.status not in _SEND_TASK_OPEN_STATES:
            return submitted
        task_id = _task_id_from_result(submitted.task)
        deadline = time.monotonic() + overall_timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            polled = await self.get_task(
                base_url,
                task_id,
                headers=headers,
                timeout=min(_SEND_TASK_ENQUEUE_HTTP_TIMEOUT_SECONDS, remaining),
            )
            if polled.status not in _SEND_TASK_OPEN_STATES:
                return polled
            await asyncio.sleep(min(_SEND_TASK_POLL_INTERVAL_SECONDS, max(remaining, 0.0)))
        raise A2AClientError(
            f"A2A task {task_id} did not complete within {overall_timeout}s"
        )

    async def get_task(
        self,
        base_url: str,
        task_id: str,
        headers: dict[str, str] | None = None,
        *,
        timeout: float | None = None,
    ) -> A2ATaskResult:
        stripped_task_id = task_id.strip()
        if not stripped_task_id:
            raise A2AClientError("GetTask task_id is required")
        params: JsonObject = {"id": stripped_task_id, "historyLength": 0}
        return await self._post_rpc(
            base_url,
            method=GET_TASK,
            params=params,
            headers=headers,
            activated_extensions=(),
            timeout=timeout,
            rpc_label="GetTask",
        )

    async def _post_rpc(
        self,
        base_url: str,
        *,
        method: str,
        params: JsonObject,
        headers: dict[str, str] | None,
        activated_extensions: Sequence[str],
        timeout: float | None,
        rpc_label: str,
    ) -> A2ATaskResult:
        url = base_url.rstrip("/")
        payload: JsonObject = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        request_headers = self._build_request_headers(
            headers,
            activated_extensions=activated_extensions,
        )
        effective_timeout = self.timeout if timeout is None else timeout
        try:
            async with get_httpx_client(
                timeout=effective_timeout,
                follow_redirects=True,
            ) as client:
                response = await client.post(url, json=payload, headers=request_headers)
                if response.status_code != 200:
                    raise A2AClientError(
                        f"Failed {rpc_label} to {url}: {response.status_code} - {response.text}"
                    )
                result = parse_json_object(response.content, f"A2A {rpc_label} response")
                if "error" in result:
                    raise A2AClientError(f"A2A error: {result['error']}")
                extension_header = cast(
                    str | None,
                    response.headers.get(A2A_EXTENSIONS_HEADER),
                )
                header_extensions = parse_a2a_extensions_header(extension_header)
                return self._parse_a2a_response(
                    result,
                    header_extensions=header_extensions,
                )
        except httpx.HTTPError as exc:
            error_str = str(exc) or type(exc).__name__
            raise A2AClientError(
                f"HTTP error {rpc_label} to {url}: {error_str}"
            ) from exc
        except ValueError as exc:
            raise A2AClientError(f"Invalid JSON response from {url}: {exc}") from exc

    def _build_request_headers(
        self,
        headers: dict[str, str] | None,
        *,
        activated_extensions: Sequence[str],
    ) -> dict[str, str]:
        request_headers = dict(headers or {})
        context = get_context()
        if context:
            if context.auth_token and "Authorization" not in request_headers:
                request_headers["Authorization"] = f"Bearer {context.auth_token}"
            if context.active_company is not None:
                request_headers.update(
                    build_internal_context_headers(
                        company_id=context.active_company.company_id,
                        user_id=context.user.user_id,
                    )
                )
            if context.active_company and "X-Company-Id" not in request_headers:
                request_headers["X-Company-Id"] = context.active_company.company_id
            if context.user and "X-User-Id" not in request_headers:
                request_headers["X-User-Id"] = context.user.user_id
            if context.trace_id and "X-Trace-Id" not in request_headers:
                request_headers["X-Trace-Id"] = context.trace_id
            if context.language and "Accept-Language" not in request_headers:
                request_headers["Accept-Language"] = context.language.value

        test_scope = resolve_test_scope()
        if test_scope is not None and TEST_SCOPE_HEADER not in request_headers:
            request_headers[TEST_SCOPE_HEADER] = test_scope

        request_headers["Content-Type"] = "application/json"
        request_headers[A2A_VERSION_HEADER] = A2A_PROTOCOL_VERSION
        if activated_extensions and A2A_EXTENSIONS_HEADER not in request_headers:
            request_headers[A2A_EXTENSIONS_HEADER] = ", ".join(
                dict.fromkeys(item.strip() for item in activated_extensions if item.strip())
            )
        return request_headers

    def _parse_a2a_response(
        self,
        raw_response: JsonObject,
        *,
        header_extensions: tuple[str, ...] = (),
    ) -> A2ATaskResult:
        task_result_value = raw_response.get("result")
        result_payload = (
            require_json_object(task_result_value, "A2A result")
            if task_result_value is not None
            else raw_response
        )
        task_result = _unwrap_send_message_task(result_payload)

        status_value = task_result.get("status")
        if status_value is None:
            raise A2AClientError("A2A response missing result.status")
        status_obj = require_json_object(status_value, "A2A result.status")
        state_value = status_obj.get("state")
        if not isinstance(state_value, str) or not state_value:
            raise A2AClientError("A2A response missing result.status.state")
        try:
            status = wire_task_state_to_platform(state_value)
        except ValueError as exc:
            raise A2AClientError(
                f"A2A response unknown result.status.state: {state_value!r}"
            ) from exc

        if status == "failed":
            error_msg = _extract_task_status_message(status_obj)
            raise A2AClientError(f"A2A task failed: {error_msg or 'unknown error'}")

        artifacts = _require_artifacts(task_result)
        try:
            response_text = extract_text_from_task_json(task_result)
        except ValueError:
            response_text = ""

        negotiated = _negotiated_extensions_from_task(task_result)
        if not negotiated and header_extensions:
            negotiated = list(header_extensions)

        return A2ATaskResult(
            task=task_result,
            artifacts=artifacts,
            status=status,
            response=response_text,
            raw=raw_response,
            negotiated_extensions=negotiated,
        )

    async def check_health(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
    ) -> bool:
        try:
            _ = await self.get_agent_card(base_url, headers)
            return True
        except (A2AClientError, httpx.HTTPError, ValueError):
            return False
