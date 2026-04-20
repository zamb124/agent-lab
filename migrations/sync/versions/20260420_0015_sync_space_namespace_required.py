"""Sync space namespace: NOT NULL + UNIQUE per company.

Жёсткое 1:1 между sync_spaces и платформенным namespace (shared KV
`namespaces`). Backfill для существующих spaces без `namespace`: генерируем
slug из `name` (с suffix space_id, чтобы избежать коллизий между
одноимёнными пространствами разных компаний и одноимёнными в одной
компании). Уникальность гарантируется индексом `(company_id, namespace)`.

После миграции UI слой Sync переключает «активное пространство» через
платформенный селект namespace (`setPlatformNamespaceSelection`) — выбор
синхронизирован с CRM/RAG.
"""

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "sync_0015"
down_revision: Union[str, None] = "sync_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SLUG_RE = re.compile(r"[^a-z0-9_-]+")
_DASHES_RE = re.compile(r"-+")


def _slug(name: str | None, suffix: str) -> str:
    """Slug в формате `^[a-z][a-z0-9_-]{0,99}$`.

    Пустое/невалидное имя -> `s-<suffix>`. Длина <= 100. Suffix добавляется
    к имени для уникальности в пределах компании при backfill.
    """
    base = _DASHES_RE.sub("-", _SLUG_RE.sub("-", (name or "").strip().lower())).strip("-")
    suffix = (suffix or "").strip().lower()[:8] or "x"
    if not base:
        out = f"s-{suffix}"
    elif not base[0].isalpha():
        out = f"s-{base}-{suffix}"
    else:
        out = f"{base}-{suffix}"
    return out[:100]


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Backfill пустых namespace для существующих spaces.
    rows = bind.execute(sa.text(
        "SELECT space_id, company_id, name, namespace "
        "FROM sync_spaces WHERE namespace IS NULL"
    )).fetchall()
    used_per_company: dict[str, set[str]] = {}
    # Предзагрузим уже существующие namespace по компаниям, чтобы избежать дубля.
    busy_rows = bind.execute(sa.text(
        "SELECT company_id, namespace FROM sync_spaces WHERE namespace IS NOT NULL"
    )).fetchall()
    for company_id, ns in busy_rows:
        used_per_company.setdefault(company_id, set()).add(ns)
    for space_id, company_id, name, _ns in rows:
        used = used_per_company.setdefault(company_id, set())
        candidate = _slug(name, str(space_id))
        # На крайний случай, если кто-то уже занят (одноимённые при backfill).
        suffix_n = 1
        while candidate in used:
            suffix_n += 1
            candidate = _slug(name, f"{str(space_id)}{suffix_n}")
        used.add(candidate)
        bind.execute(
            sa.text("UPDATE sync_spaces SET namespace = :ns WHERE space_id = :sid"),
            {"ns": candidate, "sid": space_id},
        )

    # 2. Закрепляем NOT NULL.
    op.alter_column("sync_spaces", "namespace", existing_type=sa.String(length=100), nullable=False)

    # 3. UNIQUE INDEX (company_id, namespace) — 1:1 c платформенным namespace.
    op.create_index(
        "idx_sync_spaces_company_namespace",
        "sync_spaces",
        ["company_id", "namespace"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_sync_spaces_company_namespace", table_name="sync_spaces")
    op.alter_column(
        "sync_spaces",
        "namespace",
        existing_type=sa.String(length=100),
        nullable=True,
    )
