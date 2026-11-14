"""On-demand интроспекция памяти процесса: smaps_rollup + tracemalloc diff.

Один роутер монтируется фабрикой на ``/{service}/api/internal/debug/memory``
(internal api auth — как realtime command bus). Для глубокой атрибуции
аллокаций — memray attach к процессу пода.
"""

from __future__ import annotations

import contextlib
import gc
import tracemalloc

from fastapi import APIRouter

from core.types import JsonObject


def _smaps_rollup() -> JsonObject:
    """PSS/RSS декомпозиция ``/proc/self/smaps_rollup`` — честный вес процесса."""
    keys = {
        "Rss": "rss_kb",
        "Pss": "pss_kb",
        "Pss_Anon": "pss_anon_kb",
        "Pss_File": "pss_file_kb",
        "Private_Dirty": "private_dirty_kb",
        "Shared_Clean": "shared_clean_kb",
    }
    out: JsonObject = {}
    with contextlib.suppress(OSError), open("/proc/self/smaps_rollup") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 3 and parts[0].rstrip(":") in keys:
                out[keys[parts[0].rstrip(":")]] = int(parts[1])
    return out


_trace_baseline: tracemalloc.Snapshot | None = None


def _tracemalloc_top(limit: int) -> list[JsonObject]:
    if not tracemalloc.is_tracing():
        return []
    snapshot = tracemalloc.take_snapshot()
    if _trace_baseline is not None:
        return [
            {
                "site": str(stat.traceback[0]),
                "size_kb": round(stat.size / 1024, 1),
                "size_diff_kb": round(stat.size_diff / 1024, 1),
                "count_diff": stat.count_diff,
            }
            for stat in snapshot.compare_to(_trace_baseline, "lineno")[:limit]
        ]
    return [
        {"site": str(stat.traceback[0]), "size_kb": round(stat.size / 1024, 1)}
        for stat in snapshot.statistics("lineno")[:limit]
    ]


def build_debug_memory_router(service_name: str) -> APIRouter:
    router = APIRouter()

    @router.get(f"/{service_name}/api/internal/debug/memory")
    async def memory_debug() -> JsonObject:
        return {
            "smaps_rollup": _smaps_rollup(),
            "gc_counts": list(gc.get_count()),
            "gc_tracked_objects": len(gc.get_objects()),
            "tracemalloc_tracing": tracemalloc.is_tracing(),
            "tracemalloc_top": _tracemalloc_top(10),
        }

    @router.post(f"/{service_name}/api/internal/debug/memory/trace")
    async def memory_trace_start() -> JsonObject:
        global _trace_baseline
        if not tracemalloc.is_tracing():
            tracemalloc.start(10)
        _trace_baseline = tracemalloc.take_snapshot()
        return {"tracemalloc_tracing": True, "frames": 10}

    _ = (memory_debug, memory_trace_start)
    return router
