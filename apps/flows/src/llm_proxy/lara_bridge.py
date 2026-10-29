"""Lara A2A bridge для OpenAI-compatible LLM proxy (``model=lara:<branch_id>``)."""

from __future__ import annotations

import uuid

from a2a.types import Message, Part, SendMessageRequest
from a2a.types.a2a_pb2 import ROLE_USER
from google.protobuf.json_format import MessageToDict

from apps.flows.src.channels.a2a import A2AChannel
from apps.flows.src.models.flow_config import FlowConfig
from core.a2a import extract_text_from_task_json, struct_from_mapping
from core.context import get_context
from core.office.ai_settings import LARA_DOCUMENTS_MODEL_ID, parse_lara_branch_model_id
from core.office.platform_ai_claims import OfficePlatformAiClaims
from core.types import JsonObject, require_json_object
from core.websocket import WsCommandError

_LARA_FLOW_ID = "lara"


def list_lara_branch_model_ids(branch_ids: list[str]) -> list[str]:
    """Стабильный список ``lara:<branch>`` model ids."""
    models: list[str] = []
    seen: set[str] = set()
    ordered = list(branch_ids)
    if "documents" in ordered:
        ordered.remove("documents")
        ordered.insert(0, "documents")
    for branch_id in ordered:
        model_id = f"lara:{branch_id}"
        if model_id in seen:
            continue
        seen.add(model_id)
        models.append(model_id)
    if LARA_DOCUMENTS_MODEL_ID not in seen:
        models.insert(0, LARA_DOCUMENTS_MODEL_ID)
    return models


async def load_lara_branch_ids() -> list[str]:
    flow_config = await FlowConfig.current_for_flow(_LARA_FLOW_ID)
    if flow_config is None:
        raise WsCommandError(
            "unavailable",
            "lara flow not found",
            error_code="lara_flow_not_found",
        )
    branches = flow_config.branches
    if not branches:
        raise WsCommandError(
            "unavailable",
            "lara flow has no branches",
            error_code="lara_branches_missing",
        )
    return sorted(branches.keys())


def _user_text_from_openai_messages(messages: list[JsonObject]) -> str:
    texts: list[str] = []
    for message in messages:
        role = message.get("role")
        if role not in {"user", "system"}:
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            texts.append(content.strip())
            continue
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    text_value = part.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        texts.append(text_value.strip())
    if not texts:
        raise WsCommandError(
            "ws_invalid_payload",
            "messages must contain text content",
            error_code="lara_messages_empty",
        )
    return "\n\n".join(texts)


def _extract_task_text(task_payload: JsonObject) -> str:
    try:
        return extract_text_from_task_json(task_payload)
    except ValueError as exc:
        raise WsCommandError(
            "upstream",
            "lara returned no response text",
            error_code="lara_empty_response",
        ) from exc


async def run_lara_chat_completion(
    channel: A2AChannel,
    *,
    model_id: str,
    openai_messages: list[JsonObject],
    office_ai: OfficePlatformAiClaims | None,
) -> str:
    branch_id = parse_lara_branch_model_id(model_id)
    if branch_id is None:
        raise WsCommandError(
            "ws_invalid_payload",
            f"model {model_id!r} is not lara:<branch>",
            error_code="lara_model_invalid",
            error_params={"model": model_id},
        )

    flow_config = await FlowConfig.current_for_flow(_LARA_FLOW_ID)
    if flow_config is None:
        raise WsCommandError(
            "unavailable",
            "lara flow not found",
            error_code="lara_flow_not_found",
        )
    if branch_id not in flow_config.branches:
        raise WsCommandError(
            "ws_invalid_payload",
            f"lara branch {branch_id!r} not found",
            error_code="lara_branch_not_found",
            error_params={"branch_id": branch_id},
        )

    context = get_context()
    if context is None:
        raise WsCommandError(
            "unauthorized",
            "context is not set",
            error_code="context_not_set",
        )

    user_message = _user_text_from_openai_messages(openai_messages)
    context_id = str(uuid.uuid4())
    a2a_message = Message(
        role=ROLE_USER,
        message_id=str(uuid.uuid4()),
        context_id=context_id,
        parts=[Part(text=user_message)],
    )
    metadata: JsonObject = {"branch": branch_id}
    variables: JsonObject = {}
    if office_ai is not None:
        variables["file_id"] = office_ai.file_id
        variables["catalog_id"] = ""
        variables["document_type"] = ""
        variables["route_key"] = "document_editor"
    if variables:
        metadata["variables"] = variables

    params = SendMessageRequest(
        message=a2a_message,
        metadata=struct_from_mapping(metadata),
    )
    task = await channel.on_message_send(params)
    task = await channel.on_message_send(params)
    task_payload = require_json_object(MessageToDict(task), "lara.task.payload")
    status_value = task_payload.get("status")
    if isinstance(status_value, dict):
        state = status_value.get("state")
        if state == "TASK_STATE_FAILED":
            raise WsCommandError(
                "upstream",
                "lara task failed",
                error_code="lara_task_failed",
            )
    return _extract_task_text(task_payload)


__all__ = [
    "list_lara_branch_model_ids",
    "load_lara_branch_ids",
    "run_lara_chat_completion",
]
