"""
Интеграционные тесты SMS channel (HTTP-супербаза) и отсутствия WhatsApp в flows.

БЕЗ unittest.mock / patch / MagicMock.
Реальный get_httpx_client → локальный granian sms_http_app.
"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from typing import cast

import pytest
from granian.constants import Interfaces
from granian.server.embed import Server as GranianEmbedServer
from pydantic import ValidationError

from apps.flows.src.channels.registry import create_default_channel_registry
from apps.flows.src.channels.sms import SmsChannelHandler
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models.channel_config import ChannelNodeConfig
from apps.flows.src.models.enums import ChannelType
from apps.flows.src.runtime.nodes import create_node
from core.types import JsonObject, require_json_object
from tests.flows.durable_runtime_harness import run_node, workflow_state
from tests.flows.fixtures.sms_http.main import sms_http_app


def _bind_ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host_port = cast(tuple[str, int], sock.getsockname())
    return host_port[1]


@pytest.fixture
async def sms_http_server() -> AsyncIterator[str]:
    """Реальный HTTP-сервер echo для SmsChannelHandler (granian embed)."""
    port = _bind_ephemeral_port()

    server = GranianEmbedServer(
        sms_http_app, interface=Interfaces.ASGI, address="127.0.0.1", port=port
    )
    server_task = asyncio.create_task(server.serve())

    for _ in range(50):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.1)
        connected = probe.connect_ex(("127.0.0.1", port))
        probe.close()
        if connected == 0:
            break
        await asyncio.sleep(0.1)
    else:
        _ = server.stop()
        raise RuntimeError(f"SMS HTTP echo server failed to start on port {port}")

    yield f"http://127.0.0.1:{port}"

    _ = server.stop()
    try:
        await asyncio.wait_for(server_task, timeout=5.0)
    except asyncio.TimeoutError:
        cancelled = server_task.cancel()
        _ = cancelled
        try:
            await server_task
        except asyncio.CancelledError:
            pass


def _sms_state(
    *,
    phone: str = "+79991234567",
    response: str = "Hello SMS",
    variables: JsonObject | None = None,
) -> JsonObject:
    vars_map: JsonObject = {} if variables is None else dict(variables)
    return {
        "phone": phone,
        "response": response,
        "variables": vars_map,
    }


class TestSmsChannelHandlerHttp:
    """SmsChannelHandler → реальный HTTP echo."""

    @pytest.mark.asyncio
    async def test_json_post_resolves_state_and_var(self, sms_http_server: str) -> None:
        handler = SmsChannelHandler()
        result = await handler.execute_action(
            action="send_message",
            params={},
            config={
                "preset_id": "custom",
                "url": f"{sms_http_server}/sms/echo",
                "method": "POST",
                "headers": {
                    "Authorization": "Bearer @var:sms_token",
                    "Content-Type": "application/json",
                },
                "body_template": (
                    '{"to": "@state:phone", "msg": "@state:response",'
                    + ' "api_id": "@var:sms_api_id"}'
                ),
                "timeout": 15,
            },
            variables={"sms_token": "tok-1"},
            state=_sms_state(
                variables={"sms_token": "tok-1", "sms_api_id": "api-42"},
            ),
        )
        payload = require_json_object(result, "sms.result")
        assert payload["echo"] is True
        assert payload["method"] == "POST"
        headers = require_json_object(payload["headers"], "sms.headers")
        assert headers["authorization"] == "Bearer tok-1"
        assert "application/json" in str(headers["content_type"])
        body = require_json_object(payload["json"], "sms.json")
        assert body == {
            "to": "+79991234567",
            "msg": "Hello SMS",
            "api_id": "api-42",
        }
        assert payload["form"] is None

    @pytest.mark.asyncio
    async def test_form_urlencoded_uses_form_body(self, sms_http_server: str) -> None:
        handler = SmsChannelHandler()
        result = await handler.execute_action(
            action="send_message",
            params={},
            config={
                "preset_id": "twilio",
                "url": f"{sms_http_server}/sms/echo",
                "method": "POST",
                "headers": {"Content-Type": "application/x-www-form-urlencoded"},
                "body_template": '{"To": "@state:phone", "Body": "@state:response"}',
                "timeout": 30,
            },
            variables={},
            state=_sms_state(phone="+15551234567", response="Twilio hi"),
        )
        payload = require_json_object(result, "sms.result")
        assert payload["method"] == "POST"
        headers = require_json_object(payload["headers"], "sms.headers")
        assert "application/x-www-form-urlencoded" in str(headers["content_type"])
        form = require_json_object(payload["form"], "sms.form")
        assert form == {"To": "+15551234567", "Body": "Twilio hi"}
        assert payload["json"] is None

    @pytest.mark.asyncio
    async def test_get_skips_body(self, sms_http_server: str) -> None:
        handler = SmsChannelHandler()
        result = await handler.execute_action(
            action="send_message",
            params={},
            config={
                "url": f"{sms_http_server}/sms/echo",
                "method": "GET",
                "headers": {"Content-Type": "application/json"},
                "body_template": '{"to": "@state:phone"}',
                "timeout": 10,
            },
            variables={},
            state=_sms_state(),
        )
        payload = require_json_object(result, "sms.result")
        assert payload["method"] == "GET"
        assert payload["json"] is None
        assert payload["form"] is None

    @pytest.mark.asyncio
    async def test_url_brace_from_params(self, sms_http_server: str) -> None:
        handler = SmsChannelHandler()
        result = await handler.execute_action(
            action="send_message",
            params={"account_id": "AC99"},
            config={
                "url": f"{sms_http_server}/sms/accounts/{{account_id}}/Messages.json",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "body_template": '{"Body": "@state:response"}',
            },
            variables={},
            state=_sms_state(response="path param ok"),
        )
        payload = require_json_object(result, "sms.result")
        assert payload["account_id"] == "AC99"
        assert payload["path"] == "/sms/accounts/AC99/Messages.json"
        body = require_json_object(payload["json"], "sms.json")
        # params merge into body after template
        assert body["Body"] == "path param ok"
        assert body["account_id"] == "AC99"

    @pytest.mark.asyncio
    async def test_var_in_url(self, sms_http_server: str) -> None:
        handler = SmsChannelHandler()
        twilio_vars: JsonObject = {
            "twilio_account_sid": "ACsid1",
            "twilio_basic_auth": "dXNlcjpwYXNz",
            "twilio_from_number": "+15550002222",
        }
        result = await handler.execute_action(
            action="send_message",
            params={},
            config={
                "url": f"{sms_http_server}/sms/accounts/@var:twilio_account_sid/Messages.json",
                "method": "POST",
                "headers": {
                    "Authorization": "Basic @var:twilio_basic_auth",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                "body_template": (
                    '{"To": "@state:phone", "From": "@var:twilio_from_number",'
                    + ' "Body": "@state:response"}'
                ),
            },
            variables=twilio_vars,
            state=_sms_state(
                phone="+15550001111",
                response="twilio shape",
                variables=twilio_vars,
            ),
        )
        payload = require_json_object(result, "sms.result")
        assert payload["account_id"] == "ACsid1"
        headers = require_json_object(payload["headers"], "sms.headers")
        assert headers["authorization"] == "Basic dXNlcjpwYXNz"
        form = require_json_object(payload["form"], "sms.form")
        assert form == {
            "To": "+15550001111",
            "From": "+15550002222",
            "Body": "twilio shape",
        }

    @pytest.mark.asyncio
    async def test_dict_body_template(self, sms_http_server: str) -> None:
        handler = SmsChannelHandler()
        result = await handler.execute_action(
            action="send_message",
            params={},
            config={
                "url": f"{sms_http_server}/sms/echo",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "to": "@state:phone",
                    "message": "@state:response",
                    "meta": {"api_id": "@var:sms_api_id"},
                },
            },
            variables={},
            state=_sms_state(variables={"sms_api_id": "nested-1"}),
        )
        payload = require_json_object(result, "sms.result")
        body = require_json_object(payload["json"], "sms.json")
        assert body["to"] == "+79991234567"
        assert body["message"] == "Hello SMS"
        meta = require_json_object(body["meta"], "sms.meta")
        assert meta["api_id"] == "nested-1"

    @pytest.mark.asyncio
    async def test_smsru_shaped_json_preset(self, sms_http_server: str) -> None:
        """Контракт пресета smsru (url/headers/body_template) против реального HTTP."""
        handler = SmsChannelHandler()
        result = await handler.execute_action(
            action="send_message",
            params={},
            config={
                "preset_id": "smsru",
                "url": f"{sms_http_server}/sms/echo",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "body_template": (
                    '{"api_id": "@var:sms_api_id", "to": "@state:phone",'
                    + ' "msg": "@state:response", "json": 1}'
                ),
                "timeout": 30,
            },
            variables={},
            state=_sms_state(variables={"sms_api_id": "smsru-key"}),
        )
        body = require_json_object(
            require_json_object(result, "sms.result")["json"],
            "sms.json",
        )
        assert body == {
            "api_id": "smsru-key",
            "to": "+79991234567",
            "msg": "Hello SMS",
            "json": 1,
        }

    @pytest.mark.asyncio
    async def test_http_error_raises_runtime_error(self, sms_http_server: str) -> None:
        handler = SmsChannelHandler()
        with pytest.raises(RuntimeError, match="SMS channel error: 400"):
            _ = await handler.execute_action(
                action="send_message",
                params={},
                config={
                    "url": f"{sms_http_server}/sms/fail",
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "body_template": "{}",
                },
                variables={},
                state=_sms_state(),
            )


class TestSmsChannelHandlerContract:
    """Контрактные ошибки без HTTP."""

    @pytest.mark.asyncio
    async def test_requires_url(self) -> None:
        handler = SmsChannelHandler()
        with pytest.raises(ValueError, match="url"):
            _ = await handler.execute_action(
                action="send_message",
                params={},
                config={},
                variables={},
                state=_sms_state(),
            )

    @pytest.mark.asyncio
    async def test_requires_state(self) -> None:
        handler = SmsChannelHandler()
        with pytest.raises(ValueError, match="execution state"):
            _ = await handler.execute_action(
                action="send_message",
                params={},
                config={"url": "https://example.com/sms"},
                variables={},
                state=None,
            )

    @pytest.mark.asyncio
    async def test_rejects_empty_method(self) -> None:
        handler = SmsChannelHandler()
        with pytest.raises(ValueError, match="method"):
            _ = await handler.execute_action(
                action="send_message",
                params={},
                config={"url": "https://example.com/sms", "method": "  "},
                variables={},
                state=_sms_state(),
            )

    @pytest.mark.asyncio
    async def test_rejects_non_numeric_timeout(self) -> None:
        handler = SmsChannelHandler()
        with pytest.raises(ValueError, match="timeout"):
            _ = await handler.execute_action(
                action="send_message",
                params={},
                config={
                    "url": "https://example.com/sms",
                    "timeout": "fast",
                },
                variables={},
                state=_sms_state(),
            )

    @pytest.mark.asyncio
    async def test_rejects_bool_timeout(self) -> None:
        handler = SmsChannelHandler()
        with pytest.raises(ValueError, match="timeout"):
            _ = await handler.execute_action(
                action="send_message",
                params={},
                config={"url": "https://example.com/sms", "timeout": True},
                variables={},
                state=_sms_state(),
            )

    @pytest.mark.asyncio
    async def test_rejects_invalid_body_template_type(self) -> None:
        handler = SmsChannelHandler()
        with pytest.raises(ValueError, match="body_template"):
            _ = await handler.execute_action(
                action="send_message",
                params={},
                config={
                    "url": "https://example.com/sms",
                    "method": "POST",
                    "body_template": 42,
                },
                variables={},
                state=_sms_state(),
            )

    @pytest.mark.asyncio
    async def test_rejects_unknown_action(self) -> None:
        handler = SmsChannelHandler()
        with pytest.raises(ValueError, match="send_message"):
            _ = await handler.execute_action(
                action="send_photo",
                params={},
                config={"url": "https://example.com/sms"},
                variables={},
                state=_sms_state(),
            )

    @pytest.mark.asyncio
    async def test_send_message_facade_forbidden(self) -> None:
        handler = SmsChannelHandler()
        with pytest.raises(ValueError, match="body_template"):
            _ = await handler.send_message(
                recipient="+1",
                text="hi",
                config={"url": "https://example.com/sms"},
                variables={},
            )

    @pytest.mark.asyncio
    async def test_send_photo_forbidden(self) -> None:
        handler = SmsChannelHandler()
        with pytest.raises(ValueError, match="send_message"):
            _ = await handler.send_photo(
                recipient="+1",
                photo="https://example.com/a.png",
                config={"url": "https://example.com/sms"},
                variables={},
            )

    @pytest.mark.asyncio
    async def test_send_document_forbidden(self) -> None:
        handler = SmsChannelHandler()
        with pytest.raises(ValueError, match="send_message"):
            _ = await handler.send_document(
                recipient="+1",
                document="https://example.com/a.pdf",
                config={"url": "https://example.com/sms"},
                variables={},
            )


class TestSmsChannelNode:
    """ChannelNode передаёт state= в SMS handler (durable run_node)."""

    @pytest.mark.asyncio
    async def test_channel_node_sms_resolves_state(
        self,
        sms_http_server: str,
        container: FlowRuntimeContainer,
        unique_id: str,
    ) -> None:
        flow_id = f"sms_channel_node_{unique_id}"
        node = await create_node(
            "send_sms",
            {
                "type": "channel",
                "channel": "sms",
                "action": "send_message",
                "channel_config": {
                    "preset_id": "custom",
                    "url": f"{sms_http_server}/sms/echo",
                    "method": "POST",
                    "headers": {
                        "Authorization": "Bearer @var:sms_token",
                        "Content-Type": "application/json",
                    },
                    "body_template": (
                        '{"to": "@state:phone", "message": "@state:response"}'
                    ),
                    "timeout": 30,
                },
                "input_mapping": {},
            },
            container=container,
        )
        phone = f"+7999{unique_id}"
        response_text = f"node-sms-{unique_id}"
        state = workflow_state(
            flow_id=flow_id,
            unique_id=unique_id,
            phone=phone,
            response=response_text,
            variables={"sms_token": f"tok-{unique_id}"},
        )
        result_state = await run_node(container=container, node=node, state=state)
        channel_result = require_json_object(
            result_state["channel_result"],
            "channel_result",
        )
        assert channel_result["echo"] is True
        assert channel_result["method"] == "POST"
        headers = require_json_object(channel_result["headers"], "channel.headers")
        assert headers["authorization"] == f"Bearer tok-{unique_id}"
        body = require_json_object(channel_result["json"], "channel.json")
        assert body["to"] == phone
        assert body["message"] == response_text


class TestFlowsChannelTypesCanon:
    """WhatsApp удалён из flows ChannelType; SMS зарегистрирован."""

    def test_channel_type_has_sms_not_whatsapp(self) -> None:
        values = {member.value for member in ChannelType}
        assert "sms" in values
        assert "whatsapp" not in values
        assert not hasattr(ChannelType, "WHATSAPP")

    def test_default_registry_has_sms(self) -> None:
        registry = create_default_channel_registry()
        assert registry.has(ChannelType.SMS)
        assert isinstance(registry.get(ChannelType.SMS), SmsChannelHandler)

    def test_channel_type_rejects_whatsapp_string(self) -> None:
        with pytest.raises(ValueError):
            _ = ChannelType("whatsapp")

    def test_channel_node_config_rejects_whatsapp(self) -> None:
        with pytest.raises(ValidationError):
            _ = ChannelNodeConfig.model_validate(
                {"channel": "whatsapp", "action": "send_message"}
            )

    def test_channel_node_config_accepts_sms(self) -> None:
        cfg = ChannelNodeConfig.model_validate(
            {
                "channel": "sms",
                "action": "send_message",
                "channel_config": {"url": "https://example.com/sms"},
            }
        )
        assert cfg.channel == ChannelType.SMS

    def test_channel_type_json_schema_enum(self) -> None:
        schema = ChannelNodeConfig.model_json_schema()
        schema_text = str(schema)
        assert "sms" in schema_text
        assert "whatsapp" not in schema_text
        values = {member.value for member in ChannelType}
        assert values == {"telegram", "email", "sms", "webhook"}
