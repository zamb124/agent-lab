"""Замер латентности POST /v1/audio/speech (LitServe или совместимый URL).

Субъективное A/B качества русской речи: зафиксируйте одну и ту же фразу, прогоните
эндпоинт с разными model/voice или сравните с облачным TTS (другой base_url),
затем прослушайте WAV/PCM локально.

Пример:
  uv run python scripts/benchmark_litserve_tts_latency.py \\
    --base-url http://127.0.0.1:8014/v1 --iterations 30

ENV: LITSERVE_BENCHMARK_BASE_URL — корень OpenAI-совместимого API, заканчивается на /v1.
"""

from __future__ import annotations

import argparse
import os
import statistics
import time
from urllib.parse import urljoin

import httpx


def _pctl_ms(samples_ms: list[float], q: float) -> float:
    if not samples_ms:
        raise ValueError("samples_ms must be non-empty")
    xs = sorted(samples_ms)
    k = (len(xs) - 1) * q
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return xs[f]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LITSERVE_BENCHMARK_BASE_URL", "").strip() or None,
        help="Корень API …/v1 (по умолчанию ENV LITSERVE_BENCHMARK_BASE_URL)",
    )
    parser.add_argument("--model", default="kokoro-82m-ru")
    parser.add_argument("--voice", default="")
    parser.add_argument("--text", default="Тестовая русская фраза для синтеза речи.")
    parser.add_argument("--iterations", type=int, default=25, ge=3)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--response-format", default="wav", choices=("wav", "pcm", "mp3"))
    args = parser.parse_args()
    if not args.base_url:
        raise SystemExit("Укажите --base-url или LITSERVE_BENCHMARK_BASE_URL")

    root = args.base_url.rstrip("/") + "/"
    url = urljoin(root, "audio/speech")

    body: dict[str, str] = {
        "model": args.model,
        "input": args.text,
        "response_format": args.response_format,
    }
    if args.voice.strip():
        body["voice"] = args.voice.strip()

    latencies_ms: list[float] = []
    last_bytes = 0
    with httpx.Client(timeout=args.timeout) as client:
        for i in range(args.iterations):
            t0 = time.perf_counter()
            r = client.post(url, json=body)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            r.raise_for_status()
            last_bytes = len(r.content)
            latencies_ms.append(elapsed_ms)
            print(f"  iter {i + 1}/{args.iterations}: {elapsed_ms:.1f} ms, {last_bytes} B")

    print("\n---")
    print(f"url: {url}")
    print(f"model: {args.model}  text_chars: {len(args.text)}  last_body_bytes: {last_bytes}")
    print(f"p50_ms: {statistics.median(latencies_ms):.1f}")
    print(f"p95_ms: {_pctl_ms(latencies_ms, 0.95):.1f}")
    print(f"mean_ms: {statistics.mean(latencies_ms):.1f}")


if __name__ == "__main__":
    main()
