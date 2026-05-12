"""
Отладка SSE OpenRouter: платформенный SmartProxyClient (как LLM) или сырой httpx.

Режим --client smart по умолчанию: get_httpx_client(..., strategy=SMART) и client.stream,
как в core/clients/llm/factory.py. Режим raw — прежний голый httpx.AsyncClient для A/B.

У потокового ответа два разных лимита:
- connect — только установка TCP/TLS;
- read в httpx — таймаут *между* приходом байтов; для SSE в режиме raw можно отключить
  (--read-between-chunks без аргумента). У SmartProxyClient таймаут задаётся числом timeout
  (как у LLMClient, по умолчанию 120 с): для прямого канала connect=timeout (см. SmartProxyClient._create_client).

Запуск из корня репозитория:

  uv run python scripts/debug_openrouter_sse.py
  uv run python scripts/debug_openrouter_sse.py --client raw --with-tools --wall 300
  uv run python scripts/debug_openrouter_sse.py --client direct_only --http-timeout 180
"""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import Any

import httpx

from core.config import get_settings
from core.http.client import ProxyStrategy, get_httpx_client
from core.http.egress_route_preference import (
    egress_prefer_proxy_get,
    normalized_http_origin,
    redis_key_for_origin,
)


async def _drain_sse_body(
    resp: httpx.Response,
    t0: float,
) -> tuple[int, int, bytes]:
    buf = b""
    n_chunks = 0
    n_lines = 0
    async for chunk in resp.aiter_bytes():
        n_chunks += 1
        elapsed = time.monotonic() - t0
        print(f"t={elapsed:.3f}s chunk#{n_chunks} len={len(chunk)}", flush=True)
        buf += chunk
        while True:
            if b"\n" not in buf:
                break
            raw_line, _, buf = buf.partition(b"\n")
            if raw_line.endswith(b"\r"):
                raw_line = raw_line[:-1]
            line_s = raw_line.decode("utf-8", errors="replace")
            n_lines += 1
            preview = line_s if len(line_s) <= 240 else f"{line_s[:237]}..."
            print(f"  line#{n_lines} len={len(line_s)} {preview!r}", flush=True)

    if buf:
        line_s = buf.decode("utf-8", errors="replace")
        n_lines += 1
        print(f"  tail len={len(buf)} (no final LF) {line_s[:240]!r}", flush=True)

    return n_chunks, n_lines, buf


def _platform_proxy_configured(settings: Any) -> bool:
    p = settings.proxy
    return bool(p.enabled and p.proxies)


async def _print_egress_context(
    *,
    settings: Any,
    absolute_url: str,
    strategy_label: str,
    client_mode: str,
) -> None:
    origin = normalized_http_origin(absolute_url)
    prefer = await egress_prefer_proxy_get(origin)
    proxy_on = _platform_proxy_configured(settings)
    redis_key = redis_key_for_origin(origin)
    print(
        f"debug client_mode={client_mode!r} proxy_strategy={strategy_label!r} "
        f"platform_proxy_configured={proxy_on}",
        flush=True,
    )
    print(
        f"egress origin={origin!r} redis_prefer_proxy={prefer} redis_key={redis_key!r}",
        flush=True,
    )


async def _run_with_platform_client(
    args: argparse.Namespace,
    *,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    strategy: ProxyStrategy,
    client_mode: str,
    t0: float,
) -> None:
    settings = get_settings()
    await _print_egress_context(
        settings=settings,
        absolute_url=url,
        strategy_label=strategy.value,
        client_mode=client_mode,
    )

    limits = None
    if args.no_keepalive:
        limits = httpx.Limits(max_keepalive_connections=0)

    client_kw: dict[str, Any] = {}
    if limits is not None:
        client_kw["limits"] = limits
    if args.http2:
        client_kw["http2"] = True

    http_timeout = float(args.http_timeout)
    print(
        f"t=0.000s POST {url} "
        f"(get_httpx_client timeout={http_timeout}s как у LLMClient, "
        f"strategy={strategy.value}, wall={args.wall}s)",
        flush=True,
    )

    async with get_httpx_client(
        timeout=http_timeout,
        strategy=strategy,
        **client_kw,
    ) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            elapsed = time.monotonic() - t0
            ct = resp.headers.get("content-type")
            te = resp.headers.get("transfer-encoding")
            print(
                f"t={elapsed:.3f}s status={resp.status_code} "
                f"content-type={ct!r} transfer-encoding={te!r}",
                flush=True,
            )
            resp.raise_for_status()

            wall = float(args.wall)
            if wall > 0:
                try:
                    n_chunks, n_lines, _buf = await asyncio.wait_for(
                        _drain_sse_body(resp, t0),
                        timeout=wall,
                    )
                except TimeoutError:
                    elapsed = time.monotonic() - t0
                    print(
                        f"t={elapsed:.3f}s прервано по --wall={wall}s "
                        "(общий лимит на чтение тела; не путать с паузой между чанками)",
                        flush=True,
                    )
                    raise SystemExit(124) from None
            else:
                n_chunks, n_lines, _buf = await _drain_sse_body(resp, t0)

    total = time.monotonic() - t0
    print(f"done chunks={n_chunks} lines={n_lines} total_s={total:.3f}", flush=True)


async def _run_raw_httpx(
    args: argparse.Namespace,
    *,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    t0: float,
) -> None:
    settings = get_settings()
    await _print_egress_context(
        settings=settings,
        absolute_url=url,
        strategy_label="raw_httpx",
        client_mode="raw",
    )

    connect_s = float(args.connect_timeout)
    if args.read_between_chunks is None:
        timeout = httpx.Timeout(connect=connect_s, read=None, write=60.0, pool=60.0)
    else:
        timeout = httpx.Timeout(
            connect=connect_s,
            read=float(args.read_between_chunks),
            write=60.0,
            pool=60.0,
        )

    limits = None
    if args.no_keepalive:
        limits = httpx.Limits(max_keepalive_connections=0)

    print(
        f"t=0.000s POST {url} "
        f"(raw httpx read_between_chunks={'off' if args.read_between_chunks is None else args.read_between_chunks}s, "
        f"wall={args.wall}s)",
        flush=True,
    )

    client_kw: dict[str, Any] = {
        "timeout": timeout,
        "trust_env": False,
        "http2": args.http2,
    }
    if limits is not None:
        client_kw["limits"] = limits

    async with httpx.AsyncClient(**client_kw) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            elapsed = time.monotonic() - t0
            ct = resp.headers.get("content-type")
            te = resp.headers.get("transfer-encoding")
            print(
                f"t={elapsed:.3f}s status={resp.status_code} "
                f"content-type={ct!r} transfer-encoding={te!r}",
                flush=True,
            )
            resp.raise_for_status()

            wall = float(args.wall)
            if wall > 0:
                try:
                    n_chunks, n_lines, _buf = await asyncio.wait_for(
                        _drain_sse_body(resp, t0),
                        timeout=wall,
                    )
                except TimeoutError:
                    elapsed = time.monotonic() - t0
                    print(
                        f"t={elapsed:.3f}s прервано по --wall={wall}s "
                        "(общий лимит на чтение тела; не путать с паузой между чанками)",
                        flush=True,
                    )
                    raise SystemExit(124) from None
            else:
                n_chunks, n_lines, _buf = await _drain_sse_body(resp, t0)

    total = time.monotonic() - t0
    print(f"done chunks={n_chunks} lines={n_lines} total_s={total:.3f}", flush=True)


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    cfg = settings.llm.openrouter
    if not cfg or not cfg.api_key:
        raise SystemExit("В конфиге отсутствует llm.openrouter (api_key)")

    base = str(cfg.base_url).rstrip("/")
    url = f"{base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": cfg.site_url,
        "X-Title": cfg.site_name,
    }
    if args.accept_event_stream:
        headers["Accept"] = "text/event-stream"

    body: dict[str, Any] = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.message}],
        "temperature": args.temperature,
        "stream": True,
    }
    if args.include_usage:
        body["stream_options"] = {"include_usage": True}
    if args.with_tools:
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "ask_user",
                    "description": "Задаёт вопрос пользователю",
                    "parameters": {
                        "type": "object",
                        "required": ["question"],
                        "properties": {"question": {"type": "string", "minLength": 1}},
                        "additionalProperties": False,
                    },
                },
            }
        ]

    t0 = time.monotonic()
    if args.client == "raw":
        await _run_raw_httpx(args, url=url, headers=headers, body=body, t0=t0)
        return

    strategy = ProxyStrategy.SMART if args.client == "smart" else ProxyStrategy.DIRECT_ONLY
    await _run_with_platform_client(
        args,
        url=url,
        headers=headers,
        body=body,
        strategy=strategy,
        client_mode=args.client,
        t0=t0,
    )


def main() -> None:
    p = argparse.ArgumentParser(
        description=(
            "Отладка SSE OpenRouter: по умолчанию платформенный get_httpx_client (SMART); "
            "--client raw — голый httpx для сравнения."
        )
    )
    p.add_argument(
        "--client",
        choices=("smart", "direct_only", "raw"),
        default="smart",
        help="smart: как LLM stream; direct_only: без sticky prefer и без proxy-fallback; raw: только httpx",
    )
    p.add_argument("--model", default="qwen/qwen3.5-397b-a17b")
    p.add_argument("--message", default="55")
    p.add_argument("--temperature", type=float, default=0.35)
    p.add_argument(
        "--http-timeout",
        type=float,
        default=120.0,
        help="Таймаут для get_httpx_client (как LLMClient.timeout), только smart/direct_only",
    )
    p.add_argument(
        "--connect-timeout",
        type=float,
        default=10.0,
        help="Секунды на connect TLS для режима --client raw",
    )
    p.add_argument(
        "--read-between-chunks",
        type=float,
        default=None,
        metavar="SEC",
        help=(
            "Лимит httpx read между порциями байт для режима raw. "
            "Без аргумента — отключено (рекомендуется для SSE в raw)."
        ),
    )
    p.add_argument(
        "--wall",
        type=float,
        default=600.0,
        help="Макс. секунд на всё чтение тела ответа (asyncio.wait_for); 0 = без лимита",
    )
    p.add_argument("--include-usage", action="store_true", help="Добавить stream_options.include_usage")
    p.add_argument("--with-tools", action="store_true", help="Добавить один tool ask_user")
    p.add_argument("--http2", action="store_true", help="Включить HTTP/2")
    p.add_argument(
        "--accept-event-stream",
        action="store_true",
        help="Заголовок Accept: text/event-stream на запрос",
    )
    p.add_argument(
        "--no-keepalive",
        action="store_true",
        help="httpx.Limits(max_keepalive_connections=0)",
    )
    args = p.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
