"""Bootstrap OpenFGA store + authorization model."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import cast

from core.authz.errors import AuthzConfigError
from core.authz.http_admin import create_store, write_authorization_model
from core.config import get_settings
from core.logging import get_logger
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)

_MODEL_JSON_PATH = Path(__file__).with_name("model.json")
_STORE_NAME = "platform"


def load_model_payload() -> tuple[str, list[JsonObject]]:
    if not _MODEL_JSON_PATH.is_file():
        raise AuthzConfigError(f"missing authorization model json: {_MODEL_JSON_PATH}")
    payload = require_json_object(
        cast(object, json.loads(_MODEL_JSON_PATH.read_text(encoding="utf-8"))),
        "model.json",
    )
    schema_version = payload.get("schema_version")
    type_definitions = payload.get("type_definitions")
    if not isinstance(schema_version, str) or not schema_version:
        raise AuthzConfigError("model.json schema_version is required")
    if not isinstance(type_definitions, list) or not type_definitions:
        raise AuthzConfigError("model.json type_definitions is required")
    typed_defs: list[JsonObject] = []
    for entry in type_definitions:
        typed_defs.append(require_json_object(entry, "type_definition"))
    return schema_version, typed_defs


async def bootstrap_openfga(
    *,
    api_url: str | None = None,
    api_token: str | None = None,
    store_id: str | None = None,
) -> tuple[str, str]:
    settings = get_settings()
    resolved_api_url = api_url if api_url is not None else settings.openfga.api_url
    resolved_token = api_token if api_token is not None else settings.openfga.api_token
    if not resolved_api_url:
        raise AuthzConfigError("openfga.api_url is required for bootstrap")

    resolved_store_id = store_id if store_id is not None else settings.openfga.store_id
    if not resolved_store_id:
        resolved_store_id = await create_store(
            api_url=resolved_api_url,
            name=_STORE_NAME,
            api_token=resolved_token,
        )
        logger.info("authz.openfga.store.created.store_id", store_id=resolved_store_id)

    schema_version, type_definitions = load_model_payload()
    model_id = await write_authorization_model(
        api_url=resolved_api_url,
        store_id=resolved_store_id,
        api_token=resolved_token,
        schema_version=schema_version,
        type_definitions=type_definitions,
    )
    logger.info("authz.openfga.authorization.model.written.store_id", store_id=resolved_store_id, authorization_model_id=model_id)
    return resolved_store_id, model_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap OpenFGA store and model")
    _ = parser.add_argument("--api-url", default=None)
    _ = parser.add_argument("--api-token", default=None)
    _ = parser.add_argument("--store-id", default=None)
    args = parser.parse_args(argv)
    api_url = cast(str | None, args.api_url)
    api_token = cast(str | None, args.api_token)
    store_id_arg = cast(str | None, args.store_id)
    store_id, model_id = asyncio.run(
        bootstrap_openfga(
            api_url=api_url,
            api_token=api_token,
            store_id=store_id_arg,
        )
    )
    _ = sys.stdout.write(f"store_id={store_id}\n")
    _ = sys.stdout.write(f"authorization_model_id={model_id}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
