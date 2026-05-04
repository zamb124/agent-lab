"""Диагностика WebSocket voice-сессии вне браузера.

Копировать сырой `curl ws://…` из DevTools почти всегда бесполезно: после
ответа HTTP 101 клиент должен говорить **бинарные WebSocket-фреймы**
(RFC 6455 с маской), а не «голое» тело как в HTTP.

Для проверки рукопожатия и uplink PCM используй этот скрипт (или `websocat`).
Эндпоинт принимает `company_id` в query; cookie обычно не нужны для voice,
если нет промежуточного слоя авторизации WS.

Пример::

  export VOICE_WS_COOKIE='auth_token=...'
  uv run python scripts/diagnostic_voice_ws.py \\
    'ws://system.lvh.me:8001/voice/api/ws/session/test_cli?company_id=system' \\
    --origin 'http://system.lvh.me:8001' \\
    --send-sine
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import os
import struct
from typing import Any

import websockets


def pcm16_mono_16k_sine(*, hz: float, seconds: float, sample_rate: int) -> bytes:
    n = max(1, int(seconds * sample_rate))
    blob = bytearray(n * 2)
    amp = int(32767 * 0.65)
    for i in range(n):
        sample = math.sin(2 * math.pi * hz * i / sample_rate)
        v = int(sample * amp)
        v = max(-32768, min(32767, v))
        struct.pack_into("<h", blob, i * 2, v)
    return bytes(blob)


async def run_session(
    *,
    url: str,
    origin: str | None,
    cookie_header: str,
    recv_seconds: float,
    send_sine: bool,
) -> None:
    headers: dict[str, str] = {}
    if cookie_header.strip() != "":
        headers["Cookie"] = cookie_header.strip()

    audio = pcm16_mono_16k_sine(hz=440.0, seconds=2.5, sample_rate=16_000)
    chunk_frames: list[bytes] = []
    for i in range(0, len(audio), 640):
        chunk_frames.append(audio[i : i + 640])

    loop = asyncio.get_running_loop()
    recv_deadline = loop.time() + recv_seconds

    print("connecting...", flush=True)
    async with websockets.connect(
        url,
        origin=origin,
        additional_headers=headers,
        open_timeout=15,
        ping_interval=20,
    ) as ws:
        print("connected", flush=True)

        async def sender() -> None:
            await asyncio.sleep(0.35)
            if not send_sine:
                return
            for ch in chunk_frames:
                await ws.send(ch)
                await asyncio.sleep(0.018)

        send_task = asyncio.create_task(sender())

        try:
            while loop.time() < recv_deadline:
                remaining = recv_deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=min(2.0, remaining))
                except asyncio.TimeoutError:
                    continue

                if isinstance(msg, bytes):
                    print(f"binary in: length={len(msg)}", flush=True)
                elif isinstance(msg, str):
                    try:
                        decoded: dict[str, Any] = json.loads(msg)
                        short = json.dumps(decoded, ensure_ascii=False)
                        if len(short) > 800:
                            short = short[:800] + "…"
                        print(f"text in: {short}", flush=True)
                    except json.JSONDecodeError:
                        print(f"text in (non-json): {msg[:800]}", flush=True)
                else:
                    print(f"msg: {type(msg).__name__}", flush=True)
        finally:
            send_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await send_task

        await ws.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice WS: приём media_config и тестовый PCM uplink.")
    parser.add_argument("url", help="ws://host/.../voice/api/ws/session/<id>?company_id=…")
    parser.add_argument("--origin", default=None, help="Origin (если нужен сервером/прокси), например http://system.lvh.me:8001")
    parser.add_argument(
        "--cookie",
        default=os.environ.get("VOICE_WS_COOKIE", ""),
        help="Строка Cookie или env VOICE_WS_COOKIE",
    )
    parser.add_argument("--recv-seconds", type=float, default=45.0, help="Длительность чтения входящих сообщений")
    parser.add_argument(
        "--send-sine",
        action="store_true",
        help="Отправить ~2.5 c синуса 440 Hz PCM s16le mono 16 kHz чанками ~20 ms",
    )
    args = parser.parse_args()

    asyncio.run(
        run_session(
            url=args.url,
            origin=args.origin.strip() if isinstance(args.origin, str) and args.origin.strip() != "" else None,
            cookie_header=args.cookie.strip() if isinstance(args.cookie, str) else "",
            recv_seconds=max(5.0, float(args.recv_seconds)),
            send_sine=bool(args.send_sine),
        )
    )


if __name__ == "__main__":
    main()
