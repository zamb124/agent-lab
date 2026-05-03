"""LLM bridge: замыкание STT → LLM → TTS.

Читает финальные транскрипции пользователя из `session.text_in_queue`,
прогоняет через `core.clients.llm.get_llm()` в стриме и кладёт чанки
(предложения / пред-законченные фрагменты) в `session.synthesis_queue`,
откуда `tts_worker` уже синтезирует речь.

Принципы:

* всё стримом (`.stream(...)`) — никаких ожиданий полного ответа;
* без фолбеков и `||`-дефолтов: пустой ответ LLM = `WARNING` в лог и пропуск;
* системный промпт настраивается через `voice_system_prompt`;
* при cancel сессии — просто завершаемся.
"""

from __future__ import annotations

import asyncio
from typing import Iterable, Optional

from apps.voice.services.voice_session import VoiceSession
from core.clients.llm.factory import get_llm
from core.logging import get_logger


logger = get_logger(__name__)


_DEFAULT_VOICE_SYSTEM_PROMPT = (
    "Ты голосовой ассистент. Отвечай коротко, по существу, разговорным языком. "
    "Избегай списков и markdown — твой ответ озвучивается."
)


def _split_into_speakable_chunks(buffer: str) -> tuple[list[str], str]:
    """Извлечь готовые к синтезу куски из буфера.

    Готовый кусок — заканчивается на `.`, `?`, `!`, `;` или `:`. Остаток
    (без терминатора) возвращается отдельно. Очень короткие куски
    (<3 слов) **не** отдаются — копятся дальше.
    """
    if buffer == "":
        return [], ""

    chunks: list[str] = []
    rest = buffer
    while True:
        terminators = (".", "?", "!", ";", ":", "\n")
        positions = [rest.find(t) for t in terminators]
        positions = [p for p in positions if p >= 0]
        if not positions:
            break
        cut = min(positions) + 1
        candidate = rest[:cut].strip()
        if candidate == "":
            rest = rest[cut:]
            continue
        if len(candidate.split()) < 3 and len(candidate) < 30:
            break
        chunks.append(candidate)
        rest = rest[cut:].lstrip()
        if rest == "":
            break
    return chunks, rest


async def run_llm_bridge(
    session: VoiceSession,
    *,
    model_name: Optional[str] = None,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
) -> None:
    """Бесконечный цикл моста STT → LLM → TTS.

    Завершается, когда `session.active` стал False. На каждое событие из
    `text_in_queue` запускается один LLM-стрим: его токены чанкуются по
    предложениям и кладутся в `synthesis_queue` для tts_worker.
    """
    prompt = system_prompt or _DEFAULT_VOICE_SYSTEM_PROMPT

    while session.active:
        try:
            user_text = await session.text_in_queue.get()
        except asyncio.CancelledError:
            raise

        if user_text == "":
            continue

        logger.info(
            "voice/llm/request: session_id=%s text=%s",
            session.session_id,
            user_text,
        )

        try:
            await _stream_response_to_synthesis(
                session=session,
                user_text=user_text,
                model_name=model_name,
                system_prompt=prompt,
                temperature=temperature,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "voice/llm/stream_failed: session_id=%s", session.session_id
            )


async def _stream_response_to_synthesis(
    *,
    session: VoiceSession,
    user_text: str,
    model_name: Optional[str],
    system_prompt: str,
    temperature: Optional[float],
) -> None:
    llm = get_llm(model_name=model_name, temperature=temperature)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    buffer = ""
    chunk_count = 0
    async for piece in _astream_text(llm, messages):
        if piece == "":
            continue
        buffer += piece
        speakable, rest = _split_into_speakable_chunks(buffer)
        for chunk in speakable:
            await session.synthesis_queue.put(chunk)
            chunk_count += 1
        buffer = rest

    tail = buffer.strip()
    if tail != "":
        await session.synthesis_queue.put(tail)
        chunk_count += 1

    if chunk_count == 0:
        logger.warning(
            "voice/llm/empty_response: session_id=%s user_text=%s",
            session.session_id,
            user_text,
        )


async def _astream_text(llm: object, messages: Iterable[dict[str, str]]) -> Iterable[str]:
    """Адаптер: достать текстовые токены из LangChain-совместимого стрима."""
    stream_callable = getattr(llm, "astream", None)
    if stream_callable is None:
        raise RuntimeError(
            "voice/llm: объект LLM не поддерживает .astream() — "
            "проверьте get_llm() возвращает ChatOpenAI/MockLLM."
        )

    async for chunk in stream_callable(list(messages)):
        text = _extract_text_from_chunk(chunk)
        if text != "":
            yield text


def _extract_text_from_chunk(chunk: object) -> str:
    """Достать текст из LangChain BaseMessageChunk / dict / str."""
    if isinstance(chunk, str):
        return chunk
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text")
                if isinstance(t, str):
                    parts.append(t)
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    if isinstance(chunk, dict):
        c = chunk.get("content")
        if isinstance(c, str):
            return c
    return ""


__all__ = ["run_llm_bridge"]
