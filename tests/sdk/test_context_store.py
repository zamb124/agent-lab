"""contexts.toml читается моделью, битый файл не подменяется пустым."""

from __future__ import annotations

from pathlib import Path

import pytest
from platform_sdk.context_store import PlatformContext, load_context, save_context
from platform_sdk.errors import PlatformCliError


def test_save_and_load_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "contexts.toml"
    monkeypatch.setenv("PLATFORM_CONFIG", str(path))
    monkeypatch.delenv("PLATFORM_HOST", raising=False)
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)
    save_context(
        PlatformContext(
            name="acme",
            host="https://acme.example",
            api_key="hum_secret",
            company_subdomain="acme",
        ),
        make_current=True,
    )
    loaded = load_context()
    assert loaded.name == "acme"
    assert loaded.host == "https://acme.example"
    assert loaded.api_key == "hum_secret"
    assert loaded.company_subdomain == "acme"


def test_invalid_context_file_is_an_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "contexts.toml"
    path.write_text("current = 1\n", encoding="utf-8")
    monkeypatch.setenv("PLATFORM_CONFIG", str(path))
    monkeypatch.delenv("PLATFORM_HOST", raising=False)
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)
    with pytest.raises(PlatformCliError) as caught:
        load_context()
    assert caught.value.exit_code == 2
