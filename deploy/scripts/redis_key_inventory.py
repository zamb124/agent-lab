#!/usr/bin/env python3
"""
Инвентаризация ключей Redis в кластере platform.

Сканирует db0 (DATABASE__REDIS_URL) и db1 (TASKS__BROKER_URL), агрегирует
префиксы, считает ключи без TTL и длину TaskIQ streams. Значения ключей не выводит.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class PrefixStats:
    key_count: int
    no_ttl_count: int
    sample_memory_bytes: int


TASKIQ_STREAM_NAMES: tuple[str, ...] = (
    "taskiq",
    "flows_worker",
    "idle",
    "rag",
    "sync",
    "crm",
    "search",
)


def _kubectl() -> str:
    custom = os.environ.get("KUBECTL", "").strip()
    if custom:
        return custom
    for candidate in ("kubectl", "microk8s kubectl"):
        first = candidate.split()[0]
        if subprocess.run(["which", first], capture_output=True).returncode == 0:
            return candidate
    raise RuntimeError("kubectl или microk8s не найден в PATH")


def _redis_exec(redis_cli_prefix: list[str], db: int, *args: str) -> str:
    command = [*redis_cli_prefix, "-n", str(db), *args]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise RuntimeError(f"redis-cli failed ({' '.join(command)}): {stderr}")
    return completed.stdout.strip()


def _prefix_for_key(key: str) -> str:
    if ":" in key:
        parts = key.split(":")
        if len(parts) >= 3 and parts[0] == "flows" and parts[1] == "workflow_projection":
            return "flows:workflow_projection:"
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}:"
        return f"{parts[0]}:"
    return key


def _scan_db(redis_cli_prefix: list[str], db: int, *, sample_limit: int) -> dict[str, PrefixStats]:
    prefix_counts: dict[str, int] = defaultdict(int)
    prefix_no_ttl: dict[str, int] = defaultdict(int)
    prefix_memory: dict[str, int] = defaultdict(int)
    prefix_sampled: dict[str, int] = defaultdict(int)

    cursor = "0"
    scanned = 0
    max_keys = int(os.environ.get("REDIS_INVENTORY_MAX_KEYS", "5000"))
    sample_memory_enabled = os.environ.get("REDIS_INVENTORY_SAMPLE_MEMORY", "1") == "1"
    while True:
        raw = _redis_exec(redis_cli_prefix, db, "SCAN", cursor, "COUNT", "500")
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines) < 2:
            break
        cursor = lines[0]
        keys = lines[1:]
        for key in keys:
            scanned += 1
            if scanned > max_keys:
                print(f"  (scan truncated at {max_keys} keys; set REDIS_INVENTORY_MAX_KEYS to raise)")
                return {
                    prefix: PrefixStats(
                        key_count=prefix_counts[prefix],
                        no_ttl_count=prefix_no_ttl[prefix],
                        sample_memory_bytes=prefix_memory[prefix],
                    )
                    for prefix in prefix_counts
                }
            prefix = _prefix_for_key(key)
            prefix_counts[prefix] += 1
            ttl_raw = _redis_exec(redis_cli_prefix, db, "TTL", key)
            if ttl_raw == "-1":
                prefix_no_ttl[prefix] += 1
            if sample_memory_enabled and prefix_sampled[prefix] < sample_limit:
                memory_raw = _redis_exec(redis_cli_prefix, db, "MEMORY", "USAGE", key)
                if memory_raw.isdigit():
                    prefix_memory[prefix] += int(memory_raw)
                prefix_sampled[prefix] += 1
        if cursor == "0":
            break

    return {
        prefix: PrefixStats(
            key_count=prefix_counts[prefix],
            no_ttl_count=prefix_no_ttl[prefix],
            sample_memory_bytes=prefix_memory[prefix],
        )
        for prefix in prefix_counts
    }


def _print_db_report(
    *,
    db: int,
    label: str,
    redis_cli_prefix: list[str],
    prefix_stats: dict[str, PrefixStats],
) -> None:
    dbsize = _redis_exec(redis_cli_prefix, db, "DBSIZE")
    print(f"\n=== DB{db} ({label}) DBSIZE={dbsize} ===")
    ranked = sorted(
        prefix_stats.items(),
        key=lambda item: item[1].sample_memory_bytes,
        reverse=True,
    )
    print(f"{'prefix':<40} {'keys':>8} {'no_ttl':>8} {'sample_mem':>12}")
    for prefix, stats in ranked[:25]:
        print(
            f"{prefix:<40} {stats.key_count:>8} {stats.no_ttl_count:>8} "
            f"{stats.sample_memory_bytes:>12}"
        )
    total_no_ttl = sum(stats.no_ttl_count for stats in prefix_stats.values())
    print(f"Total keys without TTL (ttl=-1): {total_no_ttl}")


def _print_stream_lengths(redis_cli_prefix: list[str], db: int) -> None:
    print(f"\n=== DB{db} TaskIQ stream lengths (XLEN) ===")
    for stream_name in TASKIQ_STREAM_NAMES:
        try:
            length = _redis_exec(redis_cli_prefix, db, "XLEN", stream_name)
        except RuntimeError:
            length = "N/A"
        print(f"  {stream_name}: {length}")
    try:
        schedule_keys_raw = _redis_exec(
            redis_cli_prefix,
            db,
            "KEYS",
            "platform_schedules*",
        )
    except RuntimeError:
        schedule_keys_raw = ""
    schedule_keys = [line.strip() for line in schedule_keys_raw.splitlines() if line.strip()]
    print(f"  platform_schedules* keys: {len(schedule_keys)}")


def main() -> int:
    namespace = os.environ.get("PLATFORM_NS", "platform")
    pod = os.environ.get("REDIS_POD", "redis-0")
    kubectl = _kubectl()
    redis_cli_prefix = [
        *kubectl.split(),
        "exec",
        "-n",
        namespace,
        pod,
        "--",
        "redis-cli",
    ]

    print("=== Redis key inventory ===")
    print(f"namespace={namespace} pod={pod}")

    for db, label in ((0, "DATABASE__REDIS_URL"), (1, "TASKS__BROKER_URL")):
        try:
            info_memory = _redis_exec(redis_cli_prefix, db, "INFO", "memory")
            used_memory = ""
            for line in info_memory.splitlines():
                if line.startswith("used_memory_human:"):
                    used_memory = line.split(":", 1)[1].strip()
                    break
            print(f"\n--- DB{db} used_memory_human={used_memory} ---")
        except RuntimeError as exc:
            print(f"\n--- DB{db} unavailable: {exc} ---")
            continue

        prefix_stats = _scan_db(redis_cli_prefix, db, sample_limit=3)
        _print_db_report(
            db=db,
            label=label,
            redis_cli_prefix=redis_cli_prefix,
            prefix_stats=prefix_stats,
        )
        if db == 1:
            _print_stream_lengths(redis_cli_prefix, db)

    return 0


if __name__ == "__main__":
    sys.exit(main())
