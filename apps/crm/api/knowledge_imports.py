"""
API журнала импорта базы знаний (мастер, список, отмена, откат).
"""

from typing import List

from fastapi import APIRouter, HTTPException, Query

from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import (
    KnowledgeImportCreatedEntitiesResponse,
    KnowledgeImportResponse,
    KnowledgeImportStartRequest,
    StructuredKnowledgeImportRequest,
)

router = APIRouter(prefix="/knowledge-imports", tags=["Knowledge imports"])


def _to_response(row) -> KnowledgeImportResponse:
    return KnowledgeImportResponse.model_validate(row)


@router.post("", response_model=KnowledgeImportResponse)
async def start_knowledge_import(
    body: KnowledgeImportStartRequest,
    container: ContainerDep,
) -> KnowledgeImportResponse:
    try:
        row = await container.knowledge_import_service.start_import(
            namespace=body.namespace,
            mode=body.mode,
            source_file_id=body.source_file_id,
            source_file_ids=body.source_file_ids,
            source_text=body.source_text,
            extract_entity_types=body.extract_entity_types,
            split_by_headings=body.split_by_headings,
            chunk_max_chars=body.chunk_max_chars,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(row)


@router.get("", response_model=List[KnowledgeImportResponse])
async def list_knowledge_imports(
    container: ContainerDep,
    namespace: str = Query(..., description="Фильтр по пространству"),
    limit: int = Query(50, ge=1, le=200),
) -> List[KnowledgeImportResponse]:
    rows = await container.knowledge_import_service.list_imports(namespace, limit=limit)
    return [_to_response(r) for r in rows]


@router.get("/{import_id}/created-entities", response_model=KnowledgeImportCreatedEntitiesResponse)
async def get_knowledge_import_created_entities(
    import_id: str,
    container: ContainerDep,
) -> KnowledgeImportCreatedEntitiesResponse:
    try:
        return await container.knowledge_import_service.get_import_created_entities(import_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Импорт не найден") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{import_id}/review-complete", response_model=KnowledgeImportResponse)
async def complete_knowledge_import_review(
    import_id: str,
    container: ContainerDep,
) -> KnowledgeImportResponse:
    try:
        row = await container.knowledge_import_service.complete_import_review(import_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Импорт не найден") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(row)


@router.get("/{import_id}", response_model=KnowledgeImportResponse)
async def get_knowledge_import(
    import_id: str,
    container: ContainerDep,
) -> KnowledgeImportResponse:
    row = await container.knowledge_import_service.get_import(import_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Импорт не найден")
    return _to_response(row)


@router.post("/{import_id}/cancel", response_model=KnowledgeImportResponse)
async def cancel_knowledge_import(
    import_id: str,
    container: ContainerDep,
) -> KnowledgeImportResponse:
    try:
        row = await container.knowledge_import_service.request_cancel(import_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/{import_id}/rollback", response_model=KnowledgeImportResponse)
async def rollback_knowledge_import(
    import_id: str,
    container: ContainerDep,
) -> KnowledgeImportResponse:
    try:
        row = await container.knowledge_import_service.rollback_import(import_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/structured/bulk")
async def structured_knowledge_import_not_implemented(
    _body: StructuredKnowledgeImportRequest,
    container: ContainerDep,
) -> None:
    raise HTTPException(
        status_code=501,
        detail="Структурированный импорт (bulk без LLM) в этой версии не реализован.",
    )
