"""
Сборка учётных данных FCM (Firebase Cloud Messaging) HTTP v1.

Источник секретов — push.fcm_credentials_json. Принимается либо строка с JSON
(для ENV PUSH__FCM_CREDENTIALS_JSON), либо уже распарсенный объект (для conf.json).
project_id берётся из самого service account, либо переопределяется push.fcm_project_id.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResolvedFcmCredentials:
    project_id: str
    client_email: str
    private_key_pem: str
    token_uri: str


def resolve_fcm_credentials(settings: Any) -> ResolvedFcmCredentials | None:
    push = settings.push
    raw = push.fcm_credentials_json
    if raw is None:
        return None

    data = _coerce_to_dict(raw)
    if data is None:
        return None

    client_email = str(data.get("client_email", "")).strip()
    private_key = str(data.get("private_key", "")).strip()
    token_uri = str(data.get("token_uri", "https://oauth2.googleapis.com/token")).strip()
    project_id_raw = push.fcm_project_id or data.get("project_id")
    project_id = str(project_id_raw).strip() if project_id_raw else ""

    if not client_email or not private_key or not project_id:
        return None

    return ResolvedFcmCredentials(
        project_id=project_id,
        client_email=client_email,
        private_key_pem=private_key,
        token_uri=token_uri,
    )


def _coerce_to_dict(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        return json.loads(text)
    return None
