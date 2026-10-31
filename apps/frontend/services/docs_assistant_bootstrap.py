"""Bootstrap при старте публичного documentation assistant."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.context import clear_context, set_context
from core.db.storage import SharedStorage
from core.docs.assistant import (
    DOCS_ASSISTANT_BRANCH_ID,
    DOCS_ASSISTANT_EMBED_ID,
    DOCS_ASSISTANT_FLOW_ID,
    DOCS_MANIFEST_STORAGE_KEY,
    DOCS_RAG_NAMESPACE_DESCRIPTION,
    DOCS_RAG_NAMESPACE_ID,
    DocsPage,
    DocsRagManifest,
    DocsRagManifestPage,
    docs_build_hash,
    load_llms_full_pages,
)
from core.identity.system_bootstrap import ensure_system_company_exists
from core.logging import get_logger
from core.models.context_models import Context
from core.models.embed_models import EmbedConfig, EmbedStatus
from core.models.i18n_models import Language
from core.models.identity_models import SYSTEM_COMPANY_ID, Company, User
from core.utils.background import run_with_log_context

logger = get_logger(__name__)

_bootstrap_task: asyncio.Task[None] | None = None


def _docs_corpus_paths(project_root: Path) -> dict[str, Path]:
    dist = project_root / "documentation-dist"
    build = project_root / "build"
    ru_dist = dist / "llms-full.txt"
    en_dist = dist / "en" / "llms-full.txt"
    return {
        "ru": ru_dist if ru_dist.is_file() else build / "documentation-ru" / "llms-full.txt",
        "en": en_dist if en_dist.is_file() else build / "documentation-en" / "llms-full.txt",
    }


def load_docs_assistant_pages(project_root: Path) -> list[DocsPage]:
    return load_llms_full_pages(_docs_corpus_paths(project_root))


def _system_user() -> User:
    return User(
        user_id="system",
        name="System",
        groups=["admin"],
        companies={SYSTEM_COMPANY_ID: ["admin"]},
        active_company_id=SYSTEM_COMPANY_ID,
        emails=["system@linnex.local"],
    )


async def _set_system_context(*, session_id: str) -> Company:
    company = await ensure_system_company_exists(
    )
    _ = set_context(
        Context(
            user=_system_user(),
            active_company=company,
            session_id=session_id,
            channel="system",
            language=Language.RU,
            trace_id=f"system:{session_id}",
        )
    )
    return company


async def ensure_docs_assistant_embed_config() -> EmbedConfig:
    """Создаёт или обновляет фиксированный public docs assistant embed в company system."""
    _ = await _set_system_context(session_id="docs_assistant_embed_bootstrap")
    try:
        previous = await EmbedConfig.get(DOCS_ASSISTANT_EMBED_ID)
        now = datetime.now(timezone.utc)
        config = EmbedConfig(
            embed_id=DOCS_ASSISTANT_EMBED_ID,
            company_id=SYSTEM_COMPANY_ID,
            name="Documentation Assistant",
            flow_id=DOCS_ASSISTANT_FLOW_ID,
            branch_id=DOCS_ASSISTANT_BRANCH_ID,
            allowed_origins=[],
            status=EmbedStatus.ACTIVE,
            theme="auto",
            position="bottom-right",
            show_launcher=False,
            primary_color="#99A6F9",
            assistant_title="Ask AI",
            interface_locale="auto",
            placeholder="Спросите по документации...",
            branding=True,
            landing_visible=False,
            guest_max_user_messages=20,
            usage_count=previous.usage_count if previous is not None else 0,
            last_used_at=previous.last_used_at if previous is not None else None,
            created_at=previous.created_at if previous is not None else now,
            created_by=(
                previous.created_by
                if previous is not None
                else "apps.frontend.services.docs_assistant_bootstrap"
            ),
            updated_at=now,
        )
        _ = await EmbedConfig.set(config)
        logger.info(
            "docs_assistant_embed_upserted",
            embed_id=config.embed_id,
            flow_id=config.flow_id,
            branch_id=config.branch_id,
        )
        return config
    finally:
        clear_context()


async def _load_manifest(storage: SharedStorage) -> DocsRagManifest:
    raw = await storage.get(DOCS_MANIFEST_STORAGE_KEY)
    if raw is None:
        return DocsRagManifest()
    try:
        return DocsRagManifest.model_validate_json(raw)
    except ValidationError as exc:
        raise ValueError("docs assistant manifest has invalid schema") from exc


async def _save_manifest(storage: SharedStorage, manifest: DocsRagManifest) -> None:
    _ = await storage.set(
        DOCS_MANIFEST_STORAGE_KEY,
        manifest.model_dump_json(),
    )


async def _delete_document_if_present(
    client: RagClient,
    *,
    namespace_id: str,
    document_id: str | None,
) -> None:
    if not document_id:
        return
    try:
        _ = await client.delete_namespace_document(namespace_id, document_id)
    except ServiceClientError:
        logger.debug(
            "docs_assistant_rag_delete_skipped",
            namespace_id=namespace_id,
            document_id=document_id,
        )


async def _sync_docs_rag_index(storage: SharedStorage, pages: list[DocsPage]) -> None:
    _ = await _set_system_context(session_id="docs_assistant_rag_bootstrap")
    try:
        client = RagClient()
        _ = await client.create_namespace(
            DOCS_RAG_NAMESPACE_ID,
            description=DOCS_RAG_NAMESPACE_DESCRIPTION,
        )
        build_hash = docs_build_hash(pages)
        manifest = await _load_manifest(storage)
        manifest_pages = dict(manifest.pages)

        current_ids = {page.document_id for page in pages}
        removed_ids = sorted(set(manifest_pages) - current_ids)
        for canonical_id in removed_ids:
            previous = manifest_pages[canonical_id]
            await _delete_document_if_present(
                client,
                namespace_id=DOCS_RAG_NAMESPACE_ID,
                document_id=previous.provider_document_id,
            )
            del manifest_pages[canonical_id]

        indexed_count = 0
        skipped_count = 0
        for page in pages:
            previous = manifest_pages.get(page.document_id)
            if (
                previous is not None
                and previous.content_hash == page.content_hash
                and previous.provider_document_id
            ):
                skipped_count += 1
                continue

            await _delete_document_if_present(
                client,
                namespace_id=DOCS_RAG_NAMESPACE_ID,
                document_id=previous.provider_document_id if previous is not None else None,
            )
            ingested = await client.ingest_text(
                DOCS_RAG_NAMESPACE_ID,
                page.text_for_rag,
                document_name=page.title,
                metadata=page.metadata(build_hash=build_hash),
                document_id=page.document_id,
            )
            manifest_pages[page.document_id] = DocsRagManifestPage(
                content_hash=page.content_hash,
                provider_document_id=ingested.document_id,
                language=page.language,
                source_url=page.source_url,
                page_title=page.title,
                updated_at=datetime.now(timezone.utc),
            )
            indexed_count += 1

        manifest.build_hash = build_hash
        manifest.updated_at = datetime.now(timezone.utc)
        manifest.namespace_id = DOCS_RAG_NAMESPACE_ID
        manifest.pages = manifest_pages
        await _save_manifest(storage, manifest)
        logger.info(
            "docs_assistant_rag_synced",
            namespace_id=DOCS_RAG_NAMESPACE_ID,
            pages=len(pages),
            indexed=indexed_count,
            skipped=skipped_count,
            removed=len(removed_ids),
        )
    finally:
        clear_context()


async def ensure_docs_assistant_ready(
    storage: SharedStorage,
    *,
    project_root: Path,
) -> None:
    _ = await ensure_docs_assistant_embed_config()
    pages = load_docs_assistant_pages(project_root)
    if not pages:
        logger.warning(
            "docs_assistant_rag_skip_no_corpus",
            project_root=str(project_root),
        )
        return
    try:
        await _sync_docs_rag_index(storage, pages)
    except Exception:
        logger.exception("docs_assistant_rag_sync_failed")


def schedule_docs_assistant_bootstrap(
    storage: SharedStorage,
    *,
    project_root: Path,
) -> None:
    global _bootstrap_task
    _bootstrap_task = run_with_log_context(
        ensure_docs_assistant_ready(storage, project_root=project_root),
        name="frontend.docs_assistant_bootstrap",
        background_kind="startup",
    )
