"""
Сборка учётных данных FCM (Firebase Cloud Messaging) HTTP v1.

Источник секретов — push.fcm_credentials_json. Принимается либо строка с JSON
(для ENV PUSH__FCM_CREDENTIALS_JSON), либо уже распарсенный объект (для conf.json).
project_id берётся из самого service account, либо переопределяется push.fcm_project_id.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.config.models import PushConfig
from core.types import JsonObject, parse_json_object


@dataclass(frozen=True)
class ResolvedFcmCredentials:
    project_id: str
    client_email: str
    private_key_pem: str
    token_uri: str


def resolve_fcm_credentials(push: PushConfig) -> ResolvedFcmCredentials | None:
    raw = push.fcm_credentials_json
    if raw is None:
        return None

    payload = _coerce_to_json_object(raw)

    client_email = _required_string(payload, "client_email")
    private_key = _required_string(payload, "private_key")
    token_uri = _required_string(payload, "token_uri")
    project_id = push.fcm_project_id.strip() if push.fcm_project_id else ""
    if not project_id:
        project_id = _required_string(payload, "project_id")

    return ResolvedFcmCredentials(
        project_id=project_id,
        client_email=client_email,
        private_key_pem=private_key,
        token_uri=token_uri,
    )


def _coerce_to_json_object(raw: str | JsonObject) -> JsonObject:
    if isinstance(raw, dict):
        return raw
    text = raw.strip()
    if not text:
        raise ValueError("push.fcm_credentials_json must be non-empty JSON")
    return parse_json_object(text, "push.fcm_credentials_json")


def _required_string(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"push.fcm_credentials_json.{key} must be a non-empty string")
    return value.strip()
