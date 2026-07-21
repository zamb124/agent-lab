"""
SmsChannelHandler — отправка SMS через HTTP-супербазу (канон External API).

channel_config: url, method, headers, body_template, timeout, preset_id (UI-метка).
В url/headers/body — @state: / @var: (MappingResolver); {key} из input_mapping params.
Сообщение живёт в body_template, не в отдельном facade recipient/text.
Ветвление по preset_id в runtime запрещено.
"""

from __future__ import annotations

from typing import override

from apps.flows.src.channels.base import BaseChannelHandler
from apps.flows.src.mapping import MappingResolver, MappingState
from apps.flows.src.models.enums import ChannelType
from core.http import get_httpx_client
from core.http.client import HttpRequestKwargs
from core.logging import get_logger
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

logger = get_logger(__name__)


class SmsChannelHandler(BaseChannelHandler):
    """
    HTTP-отправка SMS.

    Конфигурация (как External API):
    {
        "preset_id": "smsru" | "twilio" | "custom",
        "url": "https://…",
        "method": "POST",
        "headers": {"Authorization": "Bearer @var:sms_token"},
        "body_template": "{\\"to\\": \\"@state:phone\\", \\"msg\\": \\"@state:response\\"}",
        "timeout": 30
    }
    """

    channel_type: ChannelType = ChannelType.SMS

    @override
    async def execute_action(
        self,
        action: str,
        params: JsonObject,
        config: JsonObject,
        variables: JsonObject,
        state: MappingState | None = None,
    ) -> JsonObject:
        if action != "send_message":
            raise ValueError("SMS channel supports only send_message")
        if state is None:
            raise ValueError(
                "SMS channel requires execution state for @state: / @var: resolve"
            )
        return await self._send_http(
            config=config,
            variables=variables,
            state=state,
            args=params,
        )

    @override
    async def send_message(
        self,
        recipient: str,
        text: str,
        config: JsonObject,
        variables: JsonObject,
        **kwargs: JsonValue,
    ) -> JsonObject:
        _ = (recipient, text, config, variables, kwargs)
        raise ValueError(
            "SMS channel: use execute_action(..., state=execution_state); "
            + "message content belongs in body_template (@state: / @var:)"
        )

    @override
    async def send_photo(
        self,
        recipient: str,
        photo: str | bytes,
        config: JsonObject,
        variables: JsonObject,
        caption: str | None = None,
        **kwargs: JsonValue,
    ) -> JsonObject:
        _ = (recipient, photo, config, variables, caption, kwargs)
        raise ValueError("SMS channel supports only send_message")

    @override
    async def send_document(
        self,
        recipient: str,
        document: str | bytes,
        config: JsonObject,
        variables: JsonObject,
        caption: str | None = None,
        filename: str | None = None,
        **kwargs: JsonValue,
    ) -> JsonObject:
        _ = (recipient, document, config, variables, caption, filename, kwargs)
        raise ValueError("SMS channel supports only send_message")

    async def _send_http(
        self,
        *,
        config: JsonObject,
        variables: JsonObject,
        state: MappingState,
        args: JsonObject,
    ) -> JsonObject:
        url = self._resolve_url(config, args, variables, state)
        headers = self._build_headers(config, variables, state)
        method = self._resolve_method(config)
        timeout = self._resolve_timeout(config)

        json_body: JsonObject | None = None
        data_body: JsonObject | None = None
        if method != "GET":
            body = self._build_body(config, state, variables, args)
            content_type = headers.get("Content-Type", "application/json")
            if content_type.startswith("application/json"):
                json_body = body
            else:
                data_body = body

        request_kwargs: HttpRequestKwargs = {"headers": headers}
        if json_body is not None:
            request_kwargs["json"] = json_body
        if data_body is not None:
            request_kwargs["data"] = data_body

        async with get_httpx_client(timeout=timeout) as client:
            response = await client.request(method, url, **request_kwargs)

        if response.status_code >= 400:
            logger.error(
                "SMS HTTP request failed: %s - %s",
                response.status_code,
                response.text,
            )
            raise RuntimeError(
                f"SMS channel error: {response.status_code} - {response.text}"
            )

        logger.info("SMS sent via HTTP to %s: %s", url, response.status_code)
        return parse_json_object(response.content, "sms.response")

    def _resolve_method(self, config: JsonObject) -> str:
        raw_method = config.get("method", "POST")
        if not isinstance(raw_method, str) or not raw_method.strip():
            raise ValueError("sms channel_config.method must be a non-empty string")
        return raw_method.strip().upper()

    def _resolve_timeout(self, config: JsonObject) -> float:
        raw_timeout = config.get("timeout", 30.0)
        if isinstance(raw_timeout, bool) or not isinstance(raw_timeout, (int, float)):
            raise ValueError("sms channel_config.timeout must be a number")
        return float(raw_timeout)

    def _resolve_url(
        self,
        config: JsonObject,
        args: JsonObject,
        variables: JsonObject,
        state: MappingState,
    ) -> str:
        raw_url = config.get("url")
        if not isinstance(raw_url, str) or not raw_url.strip():
            raise ValueError("sms channel_config.url is required")
        resolved = MappingResolver.resolve_http_header_value(
            raw_url.strip(),
            state,
            variables,
        )
        for key, value in args.items():
            resolved = resolved.replace(f"{{{key}}}", str(value))
        if not resolved.strip():
            raise ValueError("sms channel_config.url must resolve to a non-empty string")
        return resolved.strip()

    def _build_headers(
        self,
        config: JsonObject,
        variables: JsonObject,
        state: MappingState,
    ) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        raw_headers = config.get("headers")
        if raw_headers is None:
            return headers
        config_headers = require_json_object(raw_headers, "sms.channel_config.headers")
        for key, value in config_headers.items():
            if not isinstance(value, str):
                raise ValueError(f"sms header {key!r} must be a string")
            headers[key] = MappingResolver.resolve_http_header_value(
                value,
                state,
                variables,
            )
        return headers

    def _build_body(
        self,
        config: JsonObject,
        state: MappingState,
        variables: JsonObject,
        args: JsonObject,
    ) -> JsonObject:
        raw_template = config.get("body_template")
        if raw_template is None:
            body: JsonObject = {}
        elif isinstance(raw_template, dict):
            tree = require_json_object(raw_template, "sms.channel_config.body_template")
            resolved_tree = MappingResolver.resolve_json_template_tree(
                tree,
                state,
                variables,
            )
            body = require_json_object(resolved_tree, "sms.body")
        elif isinstance(raw_template, str):
            merged = MappingResolver.parse_and_resolve_body_template(
                raw_template,
                state,
                variables,
            )
            body = require_json_object(merged, "sms.body")
        else:
            raise ValueError("sms channel_config.body_template must be a JSON string or object")

        if not args:
            return body
        return {**body, **args}


__all__ = ["SmsChannelHandler"]
