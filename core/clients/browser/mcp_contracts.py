"""
Pydantic-схемы аргументов MCP-tools Browser Runtime.

Используются на двух сторонах:
- apps/browser/api/mcp.py — валидация входа JSON-RPC tools/call.
- apps/flows/src/tools/registry.py — генерация JSON Schema для LLM (hint
  параметров MCP-tool без HTTP-запроса в browser-сервис).

Размещены в core/, чтобы flows и browser не зависели друг от друга на
уровне Python-импорта (architecture.mdc: peer-сервисы общаются только
через HTTP/WS контракты, не через прямой import).

InteractionProfileName живёт в apps/browser/interaction/interaction_profiles.py
как часть рантайма браузера; здесь повторяется как Literal без import-зависимости,
чтобы core/ не тянуло apps/.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.types import JsonObject

BrowserInteractionProfileName = Literal["off", "fast", "human"]


class ToolCreateSessionArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    page_mode: Literal["interactive", "crawl", "lite"] = "interactive"
    shared_storage_key: str | None = None
    proxy_policy: str = ""
    anti_bot_tier: str = "gray"
    timeout_ms: int = Field(default=90_000, ge=1000)
    endpoint_key: str | None = None
    session_mode: Literal["warm", "restore"] = "warm"
    restore_state_key: str | None = None
    interaction_profile: BrowserInteractionProfileName = "human"
    interaction_seed: int | None = None
    context: JsonObject = Field(default_factory=dict)


class ToolNavigateArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str
    url: str
    wait_policy: str = "domcontentloaded"
    screenshot: bool = False
    snapshot: bool = False
    capture_pdf: bool = False
    navigation_timeout_ms: int = Field(default=5_000, ge=1000)
    new_tab: bool = True


class ToolObserveArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str
    include_snapshot_refs: bool = False


class ToolCloseSessionArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str
