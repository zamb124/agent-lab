"""Idempotent seed Agent Skills for platform_assistant (real platform builtins)."""

from __future__ import annotations

from pathlib import Path

from apps.flows.src.models.agent_skill import AgentSkill
from apps.flows.src.services.agent_skill_service import (
    AgentSkillCreateInput,
    AgentSkillService,
    AgentSkillUpdateInput,
    parse_skill_md,
)
from core.files.create_spec import FileCreateSpec
from core.files.file_ref import FileRef
from core.files.service import FilesService
from core.logging import get_logger

logger = get_logger(__name__)

_SEED_ROOT = (
    Path(__file__).resolve().parent.parent.parent / "bundles" / "_seed" / "agent_skills"
)

# Attached on platform_assistant main llm_node (docx-templates via depends_on only).
PLATFORM_ASSISTANT_ATTACHED_SKILL_IDS: tuple[str, ...] = (
    "document-workspace",
    "diagrams-viz",
    "knowledge-rag",
    "web-research",
    "crm-notes",
    "work-tracking",
)

# Seed order: depends_on targets before parents that list them.
_SEED_SKILL_DIRS: tuple[str, ...] = (
    "docx-templates",
    "document-workspace",
    "diagrams-viz",
    "knowledge-rag",
    "web-research",
    "crm-notes",
    "work-tracking",
)


async def seed_platform_assistant_skills(
    agent_skill_service: AgentSkillService,
    files_service: FilesService,
    company_id: str,
) -> int:
    """Upsert platform_assistant AgentSkills. Returns number of skills processed."""
    if not _SEED_ROOT.is_dir():
        raise FileNotFoundError(f"Agent skills seed root missing: {_SEED_ROOT}")

    seeded = 0
    for skill_dirname in _SEED_SKILL_DIRS:
        skill_dir = _SEED_ROOT / skill_dirname
        skill_md_path = skill_dir / "SKILL.md"
        if not skill_md_path.is_file():
            raise FileNotFoundError(f"SKILL.md missing: {skill_md_path}")
        parsed = parse_skill_md(skill_md_path.read_text(encoding="utf-8"))
        existing: AgentSkill | None
        try:
            existing = await agent_skill_service.get(parsed.agent_skill_id)
        except LookupError:
            existing = None

        references = await _resolve_reference_files(
            files_service,
            skill_dir / "references",
            existing_references=existing.references if existing is not None else [],
        )

        if existing is None:
            _ = await agent_skill_service.create(
                AgentSkillCreateInput(
                    agent_skill_id=parsed.agent_skill_id,
                    name=parsed.name,
                    description=parsed.description,
                    body_markdown=parsed.body_markdown,
                    tool_refs=parsed.tool_refs,
                    depends_on=parsed.depends_on,
                    references=references,
                    assets=[],
                    activation=parsed.activation,
                )
            )
        else:
            _ = await agent_skill_service.update(
                parsed.agent_skill_id,
                AgentSkillUpdateInput(
                    name=parsed.name,
                    description=parsed.description,
                    body_markdown=parsed.body_markdown,
                    tool_refs=parsed.tool_refs,
                    depends_on=parsed.depends_on,
                    references=references,
                    assets=[],
                    activation=parsed.activation,
                ),
            )
        seeded += 1

    logger.info(
        "platform_assistant_skills_seeded",
        company_id=company_id,
        count=seeded,
    )
    return seeded


async def ensure_platform_assistant_skills_for_company(
    agent_skill_service: AgentSkillService,
    files_service: FilesService,
    company_id: str,
) -> int:
    """Idempotent ensure of platform Agent Skills for an existing company."""
    return await seed_platform_assistant_skills(
        agent_skill_service,
        files_service,
        company_id,
    )


async def _resolve_reference_files(
    files_service: FilesService,
    references_dir: Path,
    *,
    existing_references: list[FileRef],
) -> list[FileRef]:
    if not references_dir.is_dir():
        return []
    by_name = {
        ref.original_name: ref
        for ref in existing_references
        if ref.original_name and ref.file_id
    }
    refs: list[FileRef] = []
    for path in sorted(references_dir.glob("*.md")):
        reused = by_name.get(path.name)
        if reused is not None:
            refs.append(reused)
            continue
        payload = path.read_bytes()
        record = await files_service.create(
            FileCreateSpec.model_validate(
                {
                    "source_kind": "platform_auxiliary",
                    "source_ref": {},
                    "retention": {"kind": "platform_default"},
                    "post_create": {"is_public": True},
                }
            ),
            payload,
            original_name=path.name,
            content_type="text/markdown",
        )
        refs.append(
            FileRef(
                file_id=record.file_id,
                original_name=record.original_name,
                url=record.url,
                content_type=record.content_type,
                file_size=record.file_size,
            )
        )
    return refs


__all__ = [
    "PLATFORM_ASSISTANT_ATTACHED_SKILL_IDS",
    "ensure_platform_assistant_skills_for_company",
    "seed_platform_assistant_skills",
]
