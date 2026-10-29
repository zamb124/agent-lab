"""Тесты строгих полос ``core/lanes`` на реальном Postgres (`platform_stock`).

Проверяют: сериализацию коммитов в одной полосе, параллельность разных полос,
replay по ``idempotency_key``, ``lane_busy`` по ``lock_timeout``, захват
нескольких полос без deadlock и relay неопубликованных коммитов.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest
from oxyde import atomic, execute_raw
from pydantic import BaseModel

from core.config import get_settings
from core.errors.boundary import PlatformConflictError, PlatformUnavailableError
from core.events.contract import PlatformEvent, PlatformEventMeta
from core.events.registry import register_platform_event
from core.lanes import (
    LaneCommit,
    LaneOutcome,
    LaneRun,
    LaneScope,
    lane_id_for,
    publish_lane_run,
    relay_lane_commits,
    run_in_lanes,
)
from core.utils.time import utcnow

_DB = "stock"
_TEST_EVENT_TYPE = "lanes/test/ping"


class _PingPayload(BaseModel):
    seq: int


class _PingResult(BaseModel):
    tick: int
    seq: int


register_platform_event(_TEST_EVENT_TYPE, _PingPayload, description="Lane test ping")


def _ping_event(company_id: str, seq: int) -> PlatformEvent:
    return PlatformEvent(
        type=_TEST_EVENT_TYPE,
        company_id=company_id,
        payload=_PingPayload(seq=seq).model_dump(),
        meta=PlatformEventMeta(source="system", actor_user_id="tester"),
    )


async def _run(
    lane_id: str,
    *,
    company_id: str,
    tick: int,
    key: str | None = None,
    command_type: str = "lanes/test/command",
    body_delay: float = 0.0,
    with_event: bool = False,
) -> tuple[_PingResult, LaneCommit, bool]:
    async def body(scope: LaneScope) -> LaneOutcome[_PingResult]:
        if body_delay:
            await asyncio.sleep(body_delay)
        seq = scope.seq(lane_id)
        events = [_ping_event(company_id, seq)] if with_event else []
        return LaneOutcome(result=_PingResult(tick=tick, seq=seq), events=events)

    run = await run_in_lanes(
        [lane_id],
        company_id=company_id,
        using=_DB,
        idempotency_key=key or uuid.uuid7().hex,
        command_type=command_type,
        actor_user_id="tester",
        result_type=_PingResult,
        body=body,
    )
    return run.result, run.commit, run.replayed


@pytest.mark.asyncio
async def test_same_lane_serializes_in_order() -> None:
    """Параллельные команды одной полосы коммитятся по одной, seq строго растёт."""
    company_id = f"co-{uuid.uuid7().hex[:12]}"
    lane = lane_id_for("test", company_id, "serialize")
    intervals: list[tuple[float, float]] = []
    lock = asyncio.Lock()

    async def timed_body(scope: LaneScope) -> LaneOutcome[_PingResult]:
        start = time.perf_counter()
        await asyncio.sleep(0.01)
        seq = scope.seq(lane)
        end = time.perf_counter()
        async with lock:
            intervals.append((start, end))
        return LaneOutcome(result=_PingResult(tick=0, seq=seq), events=[])

    async def one() -> int:
        run = await run_in_lanes(
            [lane],
            company_id=company_id,
            using=_DB,
            idempotency_key=uuid.uuid7().hex,
            command_type="lanes/test/command",
            actor_user_id="tester",
            result_type=_PingResult,
            body=timed_body,
        )
        return run.result.seq

    seqs = await asyncio.gather(*[one() for _ in range(6)])
    assert sorted(seqs) == list(range(1, 7)), "lane seq must be gap-free 1..6"
    ordered = sorted(intervals)
    for (prev_start, prev_end), (next_start, _next_end) in zip(ordered, ordered[1:]):
        _ = prev_start
        assert next_start >= prev_end - 0.0005, "lane bodies must not overlap"


@pytest.mark.asyncio
async def test_different_lanes_run_in_parallel() -> None:
    """Разные полосы не сериализуются друг под друга.

    4 полосы × 0.12s: сериальный режим дал бы ≥0.48s, параллельный — ~0.12s.
    Порог 0.4s отделяет их и под нагруженной машиной."""
    company_id = f"co-{uuid.uuid7().hex[:12]}"
    lanes = [lane_id_for("test", company_id, f"par-{i}") for i in range(4)]
    start = time.perf_counter()
    results = await asyncio.gather(
        *[
            _run(lane, company_id=company_id, tick=i, body_delay=0.12)
            for i, lane in enumerate(lanes)
        ]
    )
    elapsed = time.perf_counter() - start
    assert elapsed < 0.4, f"independent lanes serialized: {elapsed:.3f}s"
    assert [result.seq for result, _commit, _ in results] == [1, 1, 1, 1]


@pytest.mark.asyncio
async def test_replay_returns_receipt_without_reexecuting() -> None:
    """Повтор с тем же idempotency_key возвращает квитанцию, body не исполняется."""
    company_id = f"co-{uuid.uuid7().hex[:12]}"
    lane = lane_id_for("test", company_id, "replay")
    key = uuid.uuid7().hex
    first_result, first_commit, first_replayed = await _run(
        lane, company_id=company_id, tick=7, key=key
    )
    assert not first_replayed

    executed = False

    async def forbidden_body(scope: LaneScope) -> LaneOutcome[_PingResult]:
        nonlocal executed
        executed = True
        return LaneOutcome(result=_PingResult(tick=-1, seq=-1), events=[])

    replay = await run_in_lanes(
        [lane],
        company_id=company_id,
        using=_DB,
        idempotency_key=key,
        command_type="lanes/test/command",
        actor_user_id="tester",
        result_type=_PingResult,
        body=forbidden_body,
    )
    assert replay.replayed
    assert not executed
    assert replay.result == first_result
    assert replay.commit.lane_commit_id == first_commit.lane_commit_id

    with pytest.raises(PlatformConflictError):
        await _run(lane, company_id=company_id, tick=1, key=key, command_type="lanes/test/other")


@pytest.mark.asyncio
async def test_multi_lane_lock_order_no_deadlock() -> None:
    """[A,B] и [B,A] захватывают полосы в одном порядке — deadlock не возникает."""
    company_id = f"co-{uuid.uuid7().hex[:12]}"
    lane_a = lane_id_for("test", company_id, "m-a")
    lane_b = lane_id_for("test", company_id, "m-b")

    async def body_ab(scope: LaneScope) -> LaneOutcome[_PingResult]:
        await asyncio.sleep(0.02)
        return LaneOutcome(result=_PingResult(tick=1, seq=scope.seq(lane_a)), events=[])

    async def body_ba(scope: LaneScope) -> LaneOutcome[_PingResult]:
        await asyncio.sleep(0.02)
        return LaneOutcome(result=_PingResult(tick=2, seq=scope.seq(lane_b)), events=[])

    async def run_ab() -> None:
        await run_in_lanes(
            [lane_a, lane_b],
            company_id=company_id,
            using=_DB,
            idempotency_key=uuid.uuid7().hex,
            command_type="lanes/test/command",
            actor_user_id="tester",
            result_type=_PingResult,
            body=body_ab,
        )

    async def run_ba() -> None:
        await run_in_lanes(
            [lane_b, lane_a],
            company_id=company_id,
            using=_DB,
            idempotency_key=uuid.uuid7().hex,
            command_type="lanes/test/command",
            actor_user_id="tester",
            result_type=_PingResult,
            body=body_ba,
        )

    await asyncio.wait_for(asyncio.gather(run_ab(), run_ba()), timeout=10)


@pytest.mark.asyncio
async def test_lock_timeout_maps_to_lane_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Строка полосы, удерживаемая другой транзакцией дольше lock_timeout — lane_busy."""
    company_id = f"co-{uuid.uuid7().hex[:12]}"
    lane = lane_id_for("test", company_id, "busy")
    await _run(lane, company_id=company_id, tick=0)  # строка курсора существует

    locked = asyncio.Event()
    release = asyncio.Event()

    async def holder() -> None:
        async with atomic(using=_DB):
            _ = await execute_raw(
                "UPDATE lane_cursors SET updated_at = updated_at WHERE lane_id = $1",
                [lane],
                using=_DB,
            )
            locked.set()
            await release.wait()

    holder_task = asyncio.create_task(holder())
    await locked.wait()
    lanes_config = get_settings().lanes
    monkeypatch.setattr(lanes_config, "lock_timeout_ms", 150)
    try:
        with pytest.raises(PlatformUnavailableError):
            await _run(lane, company_id=company_id, tick=1)
    finally:
        release.set()
        await holder_task

    # Полоса снова доступна, seq без пропусков.
    result, _commit, _ = await _run(lane, company_id=company_id, tick=2)
    assert result.seq == 2


@pytest.mark.asyncio
async def test_relay_publishes_pending_commit(service_processes) -> None:
    """Коммит без быстрого пути публикуется relay ровно один раз."""
    _ = service_processes
    company_id = f"co-{uuid.uuid7().hex[:12]}"
    lane = lane_id_for("test", company_id, "relay")
    result, commit, _ = await _run(lane, company_id=company_id, tick=3, with_event=True)
    assert result.seq == 1
    assert commit.published_at is None

    # Relay по нашей полосе: глобальный sweep под xdist заполняет limit
    # чужими коммитами и публикует события чужого каталога — scoped вызов
    # детерминированно доезжает именно наш коммит.
    relayed = await relay_lane_commits(
        using=_DB, created_before=utcnow(), limit=100, lane_id=lane
    )
    # 0 возможен: чужой глобальный sweep (maintenance-тик соседнего воркера)
    # мог опубликовать наш коммит до нас — проверка ниже на факт.
    assert relayed in (0, 1)
    stored = await LaneCommit.by_lane_commit_id(commit.lane_commit_id, using=_DB)
    assert stored is not None
    assert stored.published_at is not None

    # Повторный scoped relay не дублирует коммит.
    again = await relay_lane_commits(
        using=_DB, created_before=utcnow(), limit=100, lane_id=lane
    )
    assert again == 0
    pending = await LaneCommit.list_unpublished_by_lane_id_and_lane_seq_asc(
        created_before=utcnow(), limit=1000, using=_DB, lane_id=lane
    )
    assert pending == []
    still = await LaneCommit.by_lane_commit_id(commit.lane_commit_id, using=_DB)
    assert still is not None and still.published_at is not None

    # Повтор команды с тем же ключом — replay; publish_lane_run допубликует безопасно.
    replay_result, replay_commit, replayed = await _run(
        lane, company_id=company_id, tick=99, key=commit.idempotency_key
    )
    assert replayed
    await publish_lane_run(
        LaneRun(result=replay_result, commit=replay_commit, replayed=True), using=_DB
    )
