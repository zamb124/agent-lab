"""Per-test ресурсы процесса: RSS peak/delta, CPU-time, sys.modules.

Замеры always-on (микросекунды на rusage/proc), отчёт в конце сессии.
Атрибуция по воркеру xdist: один gw-процесс исполняет тесты последовательно,
поэтому RSS/CPU дельты фазы call принадлежат тесту. Python-аллокатор не
возвращает память ОС, поэтому rss_delta — это «кто первый поднял потолок»,
а не утечка каждого теста; утечка видна как рост peak_rss_mb по ходу сьюта.

Бюджет: тест выше PLATFORM_TEST_RSS_DELTA_FAIL_MB / PLATFORM_TEST_CPU_FAIL_S
роняет сессию. Полы warn/fail — в plugin.py.
"""

from __future__ import annotations

import json
import os
import resource
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from core.types import JsonObject, JsonValue, parse_json_object


def _rss_peak_mb() -> float:
    """ru_maxrss: KB на linux, bytes на darwin. Возвращает MiB."""
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return raw / (1024 * 1024)
    return raw / 1024


def _rss_current_mb() -> float | None:
    """VmRSS из procfs; на darwin None — там только peak."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        return None
    return None


def _cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def metric(row: JsonObject, key: str) -> float:
    """Числовое поле строки отчёта; нечисловое/отсутствующее → 0."""
    value = row.get(key)
    return float(value) if isinstance(value, int | float) else 0.0


def _worker_label() -> str:
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if not worker:
        return "master"
    if worker.startswith("gw"):
        return worker
    return f"gw{worker}"


@dataclass(slots=True)
class TestResourceSample:
    nodeid: str
    outcome: str
    worker: str
    wall_s: float
    cpu_s: float
    rss_peak_mb: float
    rss_delta_mb: float | None
    modules_delta: int

    def as_json(self) -> JsonObject:
        return {
            "nodeid": self.nodeid,
            "outcome": self.outcome,
            "worker": self.worker,
            "wall_s": self.wall_s,
            "cpu_s": self.cpu_s,
            "rss_peak_mb": self.rss_peak_mb,
            "rss_delta_mb": self.rss_delta_mb,
            "modules_delta": self.modules_delta,
        }


@dataclass
class ResourceCollector:
    samples: list[TestResourceSample] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _wall_start: float = field(default=0.0, repr=False)
    _cpu_start: float = field(default=0.0, repr=False)
    _rss_start: float | None = field(default=None, repr=False)
    _modules_start: int = field(default=0, repr=False)

    def begin_test(self) -> None:
        with self._lock:
            self._wall_start = time.monotonic()
            self._cpu_start = _cpu_seconds()
            self._rss_start = _rss_current_mb()
            self._modules_start = len(sys.modules)

    def end_test(self, nodeid: str, outcome: str) -> None:
        rss_after = _rss_current_mb()
        rss_delta: float | None = None
        if self._rss_start is not None and rss_after is not None:
            rss_delta = rss_after - self._rss_start
        sample = TestResourceSample(
            nodeid=nodeid,
            outcome=outcome,
            worker=_worker_label(),
            wall_s=time.monotonic() - self._wall_start,
            cpu_s=_cpu_seconds() - self._cpu_start,
            rss_peak_mb=_rss_peak_mb(),
            rss_delta_mb=rss_delta,
            modules_delta=len(sys.modules) - self._modules_start,
        )
        with self._lock:
            self.samples.append(sample)

    def write_report(self, path: Path) -> None:
        with self._lock:
            rows = [sample.as_json() for sample in self.samples]
        rows.sort(key=lambda row: metric(row, "cpu_s"), reverse=True)
        payload: JsonObject = {
            "worker": _worker_label(),
            "rss_peak_mb": _rss_peak_mb(),
            "samples": rows,
        }
        _ = path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class MergedResourceReport(TypedDict):
    workers: list[str]
    worker_peak_rss_mb: dict[str, float]
    samples: list[JsonObject]


def _json_rows(value: JsonValue | None) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def merge_worker_reports(report_paths: list[Path]) -> MergedResourceReport:
    samples: list[JsonObject] = []
    workers: list[str] = []
    worker_peak: dict[str, float] = {}
    for report_path in report_paths:
        if not report_path.is_file():
            continue
        try:
            payload = parse_json_object(report_path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        worker = payload.get("worker")
        worker_name = worker if isinstance(worker, str) else report_path.stem
        workers.append(worker_name)
        peak = payload.get("rss_peak_mb")
        if isinstance(peak, int | float):
            worker_peak[worker_name] = float(peak)
        samples.extend(_json_rows(payload.get("samples")))
    samples.sort(key=lambda row: metric(row, "cpu_s"), reverse=True)
    return {"workers": workers, "worker_peak_rss_mb": worker_peak, "samples": samples}


_resources_collector = ResourceCollector()


def get_resources_collector() -> ResourceCollector:
    return _resources_collector


def default_resources_report_path() -> Path:
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    return Path(f"/tmp/platform_test_resources_{worker}.json")
