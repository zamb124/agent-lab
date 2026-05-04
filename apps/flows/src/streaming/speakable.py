"""Speakable-контракт: какие A2A-артефакты озвучиваются TTS.

Flows — сервис *логики* (A2A), voice — универсальный *media gateway*. Оба
ничего не знают друг о друге. Связка живёт **на клиенте** (web-JS bridge
в ``core/frontend/static/lib/voice/``, native-bridge в мобильном
приложении): клиент читает A2A-стрим из flows и решает, какие чанки
отправить в voice через WS-команду ``speak``.

Чтобы «voice-режим» чатов (flows / embed / mobile) не зависел от того,
**как** конкретная нода или тул сгенерировали ответ, признак «это надо
озвучить» публикуется самим flows вместе с каждым артефактом. Этот файл —
единственный источник правды, **что** озвучивается; клиент-bridge лишь
следует ему без интерпретации.

### Правило

Озвучивается только ``TaskArtifactUpdateEvent`` с именем артефакта из
whitelist (:data:`SPEAKABLE_ARTIFACT_NAMES`). Всё остальное (``reasoning``,
``tool_call_*``, ``tool_result_*``, ``node_*``, ``edge_*``, ``ui_event`` и
прочие служебные имена из :mod:`apps.flows.src.streaming.base`) — **не**
озвучивается.

Опциональный negative-override: если у артефакта в ``artifact.metadata``
установлен ``speak=False``, он не озвучивается даже при whitelisted имени.
Это нужно, чтобы нода могла добавить текст в чат (ссылку, цитату,
Markdown-таблицу и т. д.), но не кормить его в TTS.

Позитивного override (``speak=True`` для не-whitelisted) нет намеренно:
правило «одно имя — один способ трактовки» защищает от случайной озвучки
служебных данных.

### Как новой ноде «говорить вслух» посреди графа

Достаточно выпустить артефакт с именем ``response`` (или другим из
whitelist) через уже существующий ``Emitter.emit_text(...)`` — он попадёт
в SSE/WS-поток A2A, отрисуется в UI-чате и одновременно будет озвучен
клиентским bridge.

### Контракт метаданных

:data:`SPEAK_FLAG_KEY` — ``"speak"``. ``artifact.metadata[SPEAK_FLAG_KEY]``
имеет тип ``bool``:

* ``True`` (или отсутствие ключа) — озвучивается, если имя whitelisted;
* ``False`` — не озвучивается даже при whitelisted имени.

### Зеркало на клиенте

JS-эквивалент констант и функции ``is_speakable_artifact`` живёт в
``core/frontend/static/lib/voice/speakable.js``. Оба файла обязаны
изменяться парно; расхождение контракта = фейл CI (см. ``voice.mdc``).
"""

from __future__ import annotations

from typing import Iterable, Optional

from a2a.types import Artifact, TaskArtifactUpdateEvent, TextPart


SPEAKABLE_ARTIFACT_NAMES: frozenset[str] = frozenset(
    {
        "response",
        "operator_reply",
    }
)
"""Whitelist имён артефактов, текст которых отправляется в TTS."""


SPEAK_FLAG_KEY: str = "speak"
"""Ключ в ``artifact.metadata`` для явного negative-override."""


def is_speakable_artifact(artifact: Artifact) -> bool:
    """True, если артефакт должен быть озвучен TTS.

    * имя в :data:`SPEAKABLE_ARTIFACT_NAMES`;
    * ``metadata.get(SPEAK_FLAG_KEY)`` не равен ``False`` (если ключ
      отсутствует — считаем разрешённым).
    """
    name = artifact.name or ""
    if name not in SPEAKABLE_ARTIFACT_NAMES:
        return False
    metadata = artifact.metadata or {}
    flag = metadata.get(SPEAK_FLAG_KEY)
    if flag is False:
        return False
    return True


def iter_speakable_text_parts(artifact: Artifact) -> Iterable[str]:
    """Выдать только текстовые части speakable-артефакта.

    ``DataPart`` / ``FilePart`` — пропускаются: их нельзя синтезировать в
    речь без потери смысла.
    """
    if not is_speakable_artifact(artifact):
        return
    for part in artifact.parts:
        root = getattr(part, "root", part)
        if isinstance(root, TextPart):
            text = root.text
            if text:
                yield text


def extract_speakable_text(event: TaskArtifactUpdateEvent) -> Optional[str]:
    """Собрать весь speakable-текст из ``TaskArtifactUpdateEvent``.

    Возвращает:

    * ``None`` — если событие не speakable (служебный артефакт, reasoning,
      negative-override, или нет текста).
    * строку — конкатенацию всех ``TextPart.text`` артефакта.
    """
    artifact = event.artifact
    if artifact is None:
        return None
    if not is_speakable_artifact(artifact):
        return None
    text_parts = list(iter_speakable_text_parts(artifact))
    if not text_parts:
        return None
    combined = "".join(text_parts)
    return combined if combined != "" else None


__all__ = [
    "SPEAKABLE_ARTIFACT_NAMES",
    "SPEAK_FLAG_KEY",
    "is_speakable_artifact",
    "iter_speakable_text_parts",
    "extract_speakable_text",
]
