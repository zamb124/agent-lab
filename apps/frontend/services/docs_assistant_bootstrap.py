"""Startup bootstrap for the public documentation assistant."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.context import Context, clear_context, set_context
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
from core.identity.system_bootstrap import (
    SYSTEM_COMPANY_ID,
    ensure_system_company_exists,
)
from core.logging import get_logger
from core.models.embed_models import EmbedConfig, EmbedMapping, EmbedStatus
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.utils.background import run_with_log_context

if TYPE_CHECKING:
    from fastapi import FastAPI

    from apps.frontend.container import FrontendContainer

logger = get_logger(__name__)


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
        emails=["system@humanitec.local"],
    )


async def _set_system_context(container: "FrontendContainer", *, session_id: str) -> Company:
    company = await ensure_system_company_exists(
        company_repository=container.company_repository,
        subdomain_repository=container.subdomain_repository,
    )
    set_context(
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


async def ensure_docs_assistant_embed_config(container: "FrontendContainer") -> EmbedConfig:
    """Create or update the fixed public docs assistant embed in company system."""
    _ = await _set_system_context(container, session_id="docs_assistant_embed_bootstrap")
    try:
        repo = container.embed_config_repository
        mapping_repo = container.embed_mapping_repository
        previous = await repo.get(DOCS_ASSISTANT_EMBED_ID)
        now = datetime.now(timezone.utc)
        config = EmbedConfig(
            embed_id=DOCS_ASSISTANT_EMBED_ID,
            name="Documentation Assistant",
            flow_id=DOCS_ASSISTANT_FLOW_ID,
            branch_id=DOCS_ASSISTANT_BRANCH_ID,
            allowed_origins=[],
            status=EmbedStatus.ACTIVE,
            theme="auto",
            position="bottom-right",
            show_launcher=False,
            show_reasoning=False,
            show_tool_calls=False,
            primary_color="#99A6F9",
            greeting_message=(
                "Спросите меня по документации. Я найду нужный раздел и дам прямую ссылку."
            ),
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
        _ = await repo.set(config)
        _ = await mapping_repo.set(
            EmbedMapping(embed_id=DOCS_ASSISTANT_EMBED_ID, company_id=SYSTEM_COMPANY_ID)
        )
        logger.info(
            "docs_assistant_embed_upserted",
            embed_id=config.embed_id,
            flow_id=config.flow_id,
            branch_id=config.branch_id,
        )
        return config
    finally:
        clear_context()


async def _load_manifest(container: "FrontendContainer") -> DocsRagManifest:
    raw = await container.shared_storage.get(DOCS_MANIFEST_STORAGE_KEY)
    if raw is None:
        return DocsRagManifest()
    try:
        return DocsRagManifest.model_validate_json(raw)
    except ValidationError as exc:
        raise ValueError("docs assistant manifest has invalid schema") from exc


async def _save_manifest(container: "FrontendContainer", manifest: DocsRagManifest) -> None:
    _ = await container.shared_storage.set(
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


async def _sync_docs_rag_index(container: "FrontendContainer", pages: list[DocsPage]) -> None:
    _ = await _set_system_context(container, session_id="docs_assistant_rag_bootstrap")
    try:
        client = RagClient()
        _ = await client.create_namespace(
            DOCS_RAG_NAMESPACE_ID,
            description=DOCS_RAG_NAMESPACE_DESCRIPTION,
        )
        build_hash = docs_build_hash(pages)
        manifest = await _load_manifest(container)
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
        await _save_manifest(container, manifest)
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
    container: "FrontendContainer",
    *,
    project_root: Path,
) -> None:
    _ = await ensure_docs_assistant_embed_config(container)
    pages = load_docs_assistant_pages(project_root)
    if not pages:
        logger.warning(
            "docs_assistant_rag_skip_no_corpus",
            project_root=str(project_root),
        )
        return
    try:
        await _sync_docs_rag_index(container, pages)
    except Exception:
        logger.exception("docs_assistant_rag_sync_failed")


def schedule_docs_assistant_bootstrap(
    app: "FastAPI",
    container: "FrontendContainer",
    *,
    project_root: Path,
) -> None:
    task = run_with_log_context(
        ensure_docs_assistant_ready(container, project_root=project_root),
        name="frontend.docs_assistant_bootstrap",
        background_kind="startup",
    )
    app.state.docs_assistant_bootstrap_task = task
