"""Bootstrap helpers that talk to OpenFGA HTTP API for store/model."""

from __future__ import annotations

import json
from typing import cast

import httpx

from core.authz.errors import AuthzUnavailable
from core.types import JsonObject, require_json_object


def _auth_headers(api_token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    return headers


async def create_store(*, api_url: str, name: str, api_token: str | None) -> str:
    url = f"{api_url.rstrip('/')}/stores"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=_auth_headers(api_token),
                json={"name": name},
            )
            _ = response.raise_for_status()
            payload = require_json_object(cast(object, response.json()))
    except (httpx.HTTPError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AuthzUnavailable(f"OpenFGA create_store failed: {exc}") from exc
    store_id = payload.get("id")
    if not isinstance(store_id, str) or not store_id:
        raise AuthzUnavailable("OpenFGA create_store response missing id")
    return store_id


async def write_authorization_model(
    *,
    api_url: str,
    store_id: str,
    api_token: str | None,
    schema_version: str,
    type_definitions: list[JsonObject],
) -> str:
    url = f"{api_url.rstrip('/')}/stores/{store_id}/authorization-models"
    body: JsonObject = {
        "schema_version": schema_version,
        "type_definitions": list(type_definitions),
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers=_auth_headers(api_token),
                json=body,
            )
            _ = response.raise_for_status()
            payload = require_json_object(cast(object, response.json()))
    except (httpx.HTTPError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AuthzUnavailable(f"OpenFGA write_authorization_model failed: {exc}") from exc
    model_id = payload.get("authorization_model_id")
    if not isinstance(model_id, str) or not model_id:
        raise AuthzUnavailable(
            "OpenFGA write_authorization_model missing authorization_model_id"
        )
    return model_id
