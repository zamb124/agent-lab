#!/usr/bin/env python3
"""Последние сообщения с блоком file/audio: JSON контента + строка sync_files.

Нужен URL БД Sync (как у сервиса). Примеры:

  export DATABASE__SYNC_URL="postgresql+asyncpg://user:pass@localhost:5432/sync_db"
  uv run python scripts/inspect_sync_channel_audio_messages.py --limit 15

  uv run python scripts/inspect_sync_channel_audio_messages.py --channel-id <uuid> --limit 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any


def _ensure_asyncpg_url(url: str) -> str:
    u = url.strip()
    if "+asyncpg" in u or "+psycopg" in u:
        return u
    if u.startswith("postgresql://"):
        return "postgresql+asyncpg://" + u[len("postgresql://") :]
    raise ValueError(
        "Ожидается postgresql:// или postgresql+asyncpg:// в DATABASE__SYNC_URL",
    )


async def _run(*, sync_url: str, channel_id: str | None, limit: int) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_ensure_asyncpg_url(sync_url), pool_pre_ping=True)
    sql = text(
        """
        SELECT
            m.message_id,
            m.channel_id,
            m.sent_at,
            m.sender_user_id,
            m.status,
            m.call_id,
            c."order" AS content_order,
            c.data AS content_data,
            f.file_id AS file_row_id,
            f.original_name AS file_original_name,
            f.mime_type AS file_mime,
            f.size_bytes AS file_size,
            f.storage_url AS file_storage_url
        FROM sync_message_contents c
        INNER JOIN sync_messages m ON m.message_id = c.message_id
        LEFT JOIN sync_files f ON f.file_id = (c.data->>'file_id')
        WHERE c.type = 'file/audio'
        AND (:channel_id IS NULL OR m.channel_id = :channel_id)
        ORDER BY m.sent_at DESC
        LIMIT :limit
        """
    )
    async with engine.connect() as conn:
        res = await conn.execute(
            sql,
            {"channel_id": channel_id, "limit": limit},
        )
        rows = res.mappings().all()
    await engine.dispose()

    if len(rows) == 0:
        print("Строк не найдено (тип file/audio).")
        return

    for r in rows:
        payload: dict[str, Any] = {
            "message_id": r["message_id"],
            "channel_id": r["channel_id"],
            "sent_at": r["sent_at"].isoformat() if r["sent_at"] else None,
            "sender_user_id": r["sender_user_id"],
            "status": r["status"],
            "call_id": r["call_id"],
            "content_order": r["content_order"],
            "content_data": r["content_data"],
            "file_in_sync_files": r["file_row_id"] is not None,
            "file_id": r["content_data"].get("file_id") if isinstance(r["content_data"], dict) else None,
            "duration_ms_in_json": r["content_data"].get("duration_ms")
            if isinstance(r["content_data"], dict)
            else None,
            "sync_files": None
            if r["file_row_id"] is None
            else {
                "file_id": r["file_row_id"],
                "original_name": r["file_original_name"],
                "mime_type": r["file_mime"],
                "size_bytes": r["file_size"],
                "storage_url_set": r["file_storage_url"] is not None
                and str(r["file_storage_url"]).strip() != "",
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("---")


def main() -> None:
    p = argparse.ArgumentParser(description="Инспекция file/audio в Sync БД.")
    p.add_argument("--channel-id", default=None, help="Фильтр по channel_id")
    p.add_argument("--limit", type=int, default=25, help="Макс. строк")
    args = p.parse_args()
    sync_url = os.environ.get("DATABASE__SYNC_URL", "").strip()
    if sync_url == "":
        print(
            "Задайте DATABASE__SYNC_URL (URL БД сервиса sync), например из conf.local.json.",
            file=sys.stderr,
        )
        sys.exit(1)
    if args.limit < 1 or args.limit > 500:
        raise SystemExit("--limit должен быть 1..500")
    asyncio.run(_run(sync_url=sync_url, channel_id=args.channel_id, limit=args.limit))


if __name__ == "__main__":
    main()
