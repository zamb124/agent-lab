"""Карточки платформенных инструментов в ленте: типизированные блоки через ``ui_render``.

Каждая функция собирает блоки грамматики Flow UI и ставит render в очередь state;
публикует их runtime на ближайшей точке flush. Значения с фигурными скобками
(патчи, аргументы) передаются в ``parameters`` — они не проходят через шаблоны.
"""

from __future__ import annotations

import re
from hashlib import sha1
from typing import Literal

from apps.flows.src.flow_ui.runtime import render_conversation
from apps.flows.src.state import ExecutionState
from core.files.file_ref import FileRef
from core.types import JsonObject
from core.ui_document.document import (
    FlowUIActionPreview,
    FlowUIActionResult,
    FlowUIActionSpec,
    FlowUIActivity,
    FlowUIBlockModel,
    FlowUIBrowserPreview,
    FlowUIButton,
    FlowUIFileCard,
    FlowUIReflection,
    FlowUISkillActivity,
)
from core.ui_document.protocol import FlowUIRender

_ID_UNSAFE = re.compile(r"[^a-z0-9_-]+")
_BLOCK_ID_MAX_LENGTH = 64
_DIGEST_LENGTH = 12


def card_block_id(prefix: str, raw: str) -> str:
    """``block_id`` по шаблону грамматики из произвольного идентификатора.

    Session id и составные ключи длиннее лимита грамматики сводятся к читаемой голове
    плюс sha1-хвосту: карточка для одного и того же ``raw`` всегда получает один id.
    """
    suffix = _ID_UNSAFE.sub("-", raw.lower()).strip("-")
    block_id = f"{prefix}-{suffix}" if suffix else prefix
    if len(block_id) <= _BLOCK_ID_MAX_LENGTH:
        return block_id
    digest = sha1(raw.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]
    head_length = _BLOCK_ID_MAX_LENGTH - len(prefix) - _DIGEST_LENGTH - 2
    head = suffix[:head_length].rstrip("-")
    return f"{prefix}-{head}-{digest}"


def show_action_preview(
    state: ExecutionState,
    *,
    card_id: str,
    title: str,
    summary: str,
    parameters: JsonObject,
    apply_action: str,
    apply_payload: JsonObject,
    apply_label: str,
) -> FlowUIRender:
    """Черновик действия с кнопкой подтверждения; клик уходит ui-action ``apply_action``."""
    blocks: list[FlowUIBlockModel] = [
        FlowUIActionPreview(block_id=card_id, title=title, summary=summary, parameters=parameters),
        FlowUIButton(
            block_id=f"{card_id}-apply",
            label=apply_label,
            action=FlowUIActionSpec(name=apply_action, payload=apply_payload),
        ),
    ]
    return render_conversation(state, blocks)


def show_action_result(
    state: ExecutionState,
    *,
    card_id: str,
    title: str,
    status: Literal["success", "failed", "pending"],
    summary: str,
) -> FlowUIRender:
    return render_conversation(
        state,
        [FlowUIActionResult(block_id=card_id, title=title, status=status, summary=summary)],
    )


def show_activity(
    state: ExecutionState,
    *,
    card_id: str,
    title: str,
    status: Literal["running", "completed", "failed"],
    detail: str,
) -> FlowUIRender:
    return render_conversation(
        state,
        [FlowUIActivity(block_id=card_id, title=title, status=status, detail=detail)],
    )


def show_browser_preview(
    state: ExecutionState,
    *,
    card_id: str,
    url: str,
    title: str,
    screenshot_url: str,
    status: Literal["running", "finished", "failed"],
) -> FlowUIRender:
    return render_conversation(
        state,
        [
            FlowUIBrowserPreview(
                block_id=card_id,
                url=url,
                title=title,
                screenshot_url=screenshot_url,
                status=status,
            )
        ],
    )


def show_skill_activity(
    state: ExecutionState,
    *,
    agent_skill_id: str,
    title: str,
    status: Literal["loading", "loaded", "failed"],
) -> FlowUIRender:
    return render_conversation(
        state,
        [
            FlowUISkillActivity(
                block_id=card_block_id("skill", agent_skill_id),
                agent_skill_id=agent_skill_id,
                title=title,
                status=status,
            )
        ],
    )


def show_reflection(
    state: ExecutionState,
    *,
    card_id: str,
    text: str,
    tone: Literal["success", "warning", "error"] = "success",
    detail: str = "",
) -> FlowUIRender:
    return render_conversation(
        state,
        [FlowUIReflection(block_id=card_id, text=text, tone=tone, detail=detail)],
    )


def show_files(state: ExecutionState, files: list[FileRef]) -> FlowUIRender:
    """Карточки файлов из ``state.files`` по file_id; файлы уже должны быть в state."""
    blocks: list[FlowUIBlockModel] = []
    for file_ref in files:
        if file_ref.file_id is None:
            raise ValueError("show_files requires FileRef.file_id")
        blocks.append(
            FlowUIFileCard(
                block_id=card_block_id("file", file_ref.file_id), file_id=file_ref.file_id
            )
        )
    return render_conversation(state, blocks)


__all__ = [
    "card_block_id",
    "show_action_preview",
    "show_action_result",
    "show_activity",
    "show_browser_preview",
    "show_files",
    "show_reflection",
    "show_skill_activity",
]
