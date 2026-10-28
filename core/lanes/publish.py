"""Публикация событий коммитов полос: быстрый путь после commit и догоняющий relay.

Bus дедуплицирует ``PlatformEvent`` по ``event_id``, поэтому повторная публикация
коммита безопасна: доставка — at-least-once с идемпотентным ingest.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel

from core.config import get_settings
from core.events import publish_events
from core.lanes.models.lane_commit import LaneCommit
from core.lanes.tx import LaneRun
from core.logging import get_logger
from core.utils.time import utcnow

logger = get_logger(__name__)


async def publish_lane_commit(commit: LaneCommit, *, using: str) -> None:
    """Опубликовать события коммита и отметить его опубликованным."""
    if commit.published_at is not None:
        return
    await publish_events(commit.platform_events())
    await LaneCommit.mark_published(commit.lane_commit_id, using=using)


async def publish_lane_run[R: BaseModel](run: LaneRun[R], *, using: str) -> None:
    """Быстрый путь сразу после ``run_in_lanes``; повтор догоняет неопубликованный коммит."""
    if run.replayed:
        stored = await LaneCommit.by_lane_commit_id(run.commit.lane_commit_id, using=using)
        if stored is None:
            raise RuntimeError(f"lane commit {run.commit.lane_commit_id} disappeared")
        await publish_lane_commit(stored, using=using)
        return
    await publish_lane_commit(run.commit, using=using)


def relay_cutoff() -> datetime:
    """Коммит старше этой отметки без ``published_at`` — быстрый путь до bus не дошёл."""
    return utcnow() - timedelta(seconds=get_settings().lanes.relay_after_seconds)


def expire_cutoff() -> datetime:
    """Опубликованный коммит старше этой отметки вышел из окна идемпотентности."""
    return utcnow() - timedelta(days=get_settings().lanes.commit_retention_days)


async def relay_lane_commits(
    *,
    using: str,
    created_before: datetime,
    limit: int,
    lane_id: str | None = None,
) -> int:
    """Опубликовать коммиты, чей быстрый путь не дошёл до bus; возвращает их число.

    Глобальный sweep — фоновый tick владельца БД. ``lane_id`` — точечный
    догон одной полосы: релеер публикует только события, чей каталог он
    знает, и не трогает чужие коммиты.
    """
    commits = await LaneCommit.list_unpublished_by_lane_seq(
        created_before=created_before, limit=limit, using=using, lane_id=lane_id
    )
    for commit in commits:
        await publish_lane_commit(commit, using=using)
    if commits:
        logger.warning("lanes.relay_published", commits=len(commits), database=using)
    return len(commits)


async def expire_lane_commits(*, using: str, published_before: datetime) -> int:
    """Удалить опубликованные коммиты старше ``published_before``."""
    return await LaneCommit.expire_published(published_before=published_before, using=using)
