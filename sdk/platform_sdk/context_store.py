"""Контексты CLI: host компании и API-ключ вне репозитория."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from platform_sdk.errors import usage_error

_CONTEXTS_ENV = "PLATFORM_CONFIG"


@dataclass(frozen=True)
class PlatformContext:
    name: str
    host: str
    api_key: str
    company_subdomain: str


class StoredContext(BaseModel):
    """Один контекст в contexts.toml."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    company_subdomain: str = ""

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        return _normalize_host(value)

    @model_validator(mode="after")
    def fill_subdomain(self) -> StoredContext:
        if self.company_subdomain == "":
            self.company_subdomain = _subdomain(self.host)
        return self


class ContextsFile(BaseModel):
    """Файл ~/.config/platform/contexts.toml."""

    model_config = ConfigDict(extra="forbid")

    current: str = Field(min_length=1)
    contexts: dict[str, StoredContext]


def contexts_path() -> Path:
    override = os.environ.get(_CONTEXTS_ENV, "")
    if override != "":
        return Path(override)
    return Path.home() / ".config" / "platform" / "contexts.toml"


def load_context(name: str | None = None) -> PlatformContext:
    env_host = os.environ.get("PLATFORM_HOST", "")
    env_key = os.environ.get("PLATFORM_API_KEY", "")
    if env_host != "" and env_key != "":
        stored = StoredContext(host=env_host, api_key=env_key)
        return PlatformContext(
            name="env",
            host=stored.host,
            api_key=stored.api_key,
            company_subdomain=stored.company_subdomain,
        )
    document = _read_file(contexts_path())
    selected_name = document.current if name is None else name
    selected = document.contexts.get(selected_name)
    if selected is None:
        raise usage_error(f"Context {selected_name!r} is not in {contexts_path()}")
    return PlatformContext(
        name=selected_name,
        host=selected.host,
        api_key=selected.api_key,
        company_subdomain=selected.company_subdomain,
    )


def save_context(context: PlatformContext, *, make_current: bool) -> Path:
    path = contexts_path()
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.is_file():
        document = _read_file(path)
    else:
        document = ContextsFile(current=context.name, contexts={})
    document.contexts[context.name] = StoredContext(
        host=context.host,
        api_key=context.api_key,
        company_subdomain=context.company_subdomain,
    )
    current = context.name if make_current else document.current
    updated = document.model_copy(update={"current": current})
    path.write_text(_render(updated), encoding="utf-8")
    path.chmod(0o600)
    return path


def list_contexts() -> tuple[str, list[str]]:
    path = contexts_path()
    if not path.is_file():
        return "", []
    document = _read_file(path)
    return document.current, sorted(document.contexts)


def use_context(name: str) -> None:
    path = contexts_path()
    if not path.is_file():
        raise usage_error(f"No contexts file at {path}")
    document = _read_file(path)
    if name not in document.contexts:
        raise usage_error(f"Context {name!r} does not exist")
    path.write_text(_render(document.model_copy(update={"current": name})), encoding="utf-8")
    path.chmod(0o600)


def _read_file(path: Path) -> ContextsFile:
    if not path.is_file():
        raise usage_error(
            "No platform context. Run `platform login --host <subdomain.apex> --api-key hum_...`"
        )
    try:
        loaded = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise usage_error(f"{path}: {exc}") from exc
    try:
        return ContextsFile.model_validate(loaded)
    except ValidationError as exc:
        raise usage_error(f"{path}: {exc}") from exc


def _render(document: ContextsFile) -> str:
    lines = [f"current = {_toml_string(document.current)}", ""]
    for name in sorted(document.contexts):
        entry = document.contexts[name]
        lines.append(f"[contexts.{_toml_key(name)}]")
        lines.append(f"host = {_toml_string(entry.host)}")
        lines.append(f"api_key = {_toml_string(entry.api_key)}")
        lines.append(f"company_subdomain = {_toml_string(entry.company_subdomain)}")
        lines.append("")
    return "\n".join(lines)


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_key(name: str) -> str:
    if name.isidentifier():
        return name
    return _toml_string(name)


def _normalize_host(host: str) -> str:
    value = host.strip().rstrip("/")
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://{value}"


def _subdomain(host: str) -> str:
    bare = host.strip().removeprefix("https://").removeprefix("http://").split("/")[0]
    return bare.split(".")[0]
