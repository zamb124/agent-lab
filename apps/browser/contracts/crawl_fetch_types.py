"""One-shot browser crawl fetch HTTP contract."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.types import JsonObject


class BrowserCrawlFetchRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    url: str = Field(..., min_length=1)
    wait_policy: Literal["domcontentloaded", "networkidle"] = "domcontentloaded"
    navigation_timeout_ms: int = Field(default=30_000, ge=1000, le=120_000)
    block_resource_types: list[str] = Field(
        default_factory=lambda: ["image", "media", "font", "stylesheet"],
    )


class BrowserCrawlFetchResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    final_url: str
    status_code: int | None
    html: str
    anti_bot_signals: JsonObject = Field(default_factory=dict)
