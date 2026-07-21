"""Emulator lifecycle fixture and helpers for Google API bases."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from granian.constants import Interfaces
from granian.server.embed import Server as GranianEmbedServer

import core.clients.google_docs_client as google_docs_client_mod
import core.clients.google_sheets_client as google_sheets_client_mod
import core.config.base as config_base
from core.config.base import BaseSettings
from core.config.models import GoogleWorkspaceApiBases
from tests.fixtures.google_api_emulator.app import create_google_api_emulator_app
from tests.fixtures.google_api_emulator.store import EmulatorStore

OAUTH_USER_TOKEN = "oauth-user"
SA_COMPANY_TOKEN = "sa-company"


@dataclass(frozen=True)
class GoogleApiEmulatorHandle:
    base_url: str
    store: EmulatorStore
    api_bases: GoogleWorkspaceApiBases
    oauth_token: str
    sa_token: str

    def service_account_json(self, *, subject_email: str | None = None) -> str:
        _ = subject_email
        return make_emulator_service_account_json(token_uri=f"{self.base_url}/token")


def make_emulator_service_account_json(*, token_uri: str) -> str:
    """RSA SA JSON pointing token_uri at the local emulator."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    payload = {
        "type": "service_account",
        "project_id": "emulator",
        "private_key_id": "emulator-key",
        "private_key": pem,
        "client_email": "emulator@emulator.iam.gserviceaccount.com",
        "client_id": "100000000000000000000",
        "token_uri": token_uri,
    }
    return json.dumps(payload)


def apply_google_api_bases(
    monkeypatch: pytest.MonkeyPatch,
    api_bases: GoogleWorkspaceApiBases,
) -> None:
    """
    Point Google Sheets/Docs clients at the emulator via api_bases.

    Patches get_settings only in the Google client modules and re-applies
    api_bases on every read so mid-test google_workspace replacements cannot
    silently route traffic to production Google.
    """
    real_get_settings: Callable[[], BaseSettings] = config_base.get_settings

    def patched_get_settings() -> BaseSettings:
        current = real_get_settings()
        object.__setattr__(current.google_workspace, "api_bases", api_bases)
        return current

    object.__setattr__(
        real_get_settings().google_workspace,
        "api_bases",
        api_bases,
    )
    monkeypatch.setattr(google_sheets_client_mod, "get_settings", patched_get_settings)
    monkeypatch.setattr(google_docs_client_mod, "get_settings", patched_get_settings)


async def _wait_tcp_ready(host: str, port: int, attempts: int = 100) -> None:
    for _ in range(attempts):
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.05)
    raise RuntimeError(f"google api emulator did not open {host}:{port}")


@pytest.fixture
async def google_api_emulator(
    unused_tcp_port_factory: object,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[GoogleApiEmulatorHandle]:
    port_factory = unused_tcp_port_factory
    if not callable(port_factory):
        raise TypeError("unused_tcp_port_factory must be callable")
    port = int(port_factory())
    store = EmulatorStore()
    store.allow_token(OAUTH_USER_TOKEN)
    store.allow_token(SA_COMPANY_TOKEN)
    app = create_google_api_emulator_app(store)
    server = GranianEmbedServer(
        app, interface=Interfaces.ASGI, address="127.0.0.1", port=port
    )
    task = asyncio.create_task(server.serve())
    try:
        await _wait_tcp_ready("127.0.0.1", port)
        base_url = f"http://127.0.0.1:{port}"
        api_bases = GoogleWorkspaceApiBases(
            sheets_base=f"{base_url}/v4",
            docs_base=f"{base_url}/v1/documents",
            drive_base=f"{base_url}/drive/v3",
            drive_upload_base=f"{base_url}/upload/drive/v3/files",
            token_uri=f"{base_url}/token",
        )
        apply_google_api_bases(monkeypatch, api_bases)
        yield GoogleApiEmulatorHandle(
            base_url=base_url,
            store=store,
            api_bases=api_bases,
            oauth_token=OAUTH_USER_TOKEN,
            sa_token=SA_COMPANY_TOKEN,
        )
    finally:
        server.stop()
        await task
