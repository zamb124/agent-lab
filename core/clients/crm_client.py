"""HTTP client for CRM API on top of ServiceClient."""

from __future__ import annotations

import asyncio
import json
from datetime import date as Date
from typing import Literal
from urllib.parse import quote, urlencode

from core.clients.crm_models import (
    CrmAnalyzeNoteTextArgs,
    CrmApplyAnalysisDraftArgs,
    CrmCapabilityCreateNoteArgs,
    CrmCreateActivityTaskArgs,
    CrmCreateEntityArgs,
    CrmCreateNoteAndAnalyzeArgs,
    CrmCreateRelationshipArgs,
    CrmDailySummaryArgs,
    CrmDeleteEntityArgs,
    CrmDeleteRelationshipArgs,
    CrmDiscardAnalysisDraftArgs,
    CrmEntityRelatedArgs,
    CrmGetEntityArgs,
    CrmKnowledgeImportStatusArgs,
    CrmListActivityTasksArgs,
    CrmListEntityTypesArgs,
    CrmListNotesArgs,
    CrmListRelationshipsArgs,
    CrmListRelationshipTypesArgs,
    CrmListSuggestsArgs,
    CrmMergeEntitiesArgs,
    CrmPeriodSummaryArgs,
    CrmSearchEntitiesArgs,
    CrmShortestPathArgs,
    CrmSuggestIdArgs,
    CrmUpdateEntityArgs,
)
from core.clients.service_client import NAMESPACE_HEADER, ServiceClient
from core.context import resolve_namespace_or_raise
from core.types import JsonObject, JsonValue, require_json_array, require_json_object

_API = "/crm/api/v1"
_NOTE_ANALYZE_POLL_SEC = 120.0
_NOTE_ANALYZE_SLEEP_SEC = 0.35


class CrmClient:
    """REST client for CRM service; namespace from context via X-Platform-Namespace."""

    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._http: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )

    def _ns_headers(self) -> dict[str, str]:
        return {NAMESPACE_HEADER: resolve_namespace_or_raise()}

    def _resolve_namespace(self, namespace: str | None) -> str:
        if namespace is not None and str(namespace).strip():
            return str(namespace).strip()
        return resolve_namespace_or_raise()

    @staticmethod
    def _as_objects(value: object, label: str) -> list[JsonObject]:
        items = require_json_array(value, label)
        return [require_json_object(item, f"{label}[{index}]") for index, item in enumerate(items)]

    @staticmethod
    def _compact_entity_hit(raw: JsonObject) -> JsonObject:
        desc = raw.get("description")
        if isinstance(desc, str) and len(desc) > 400:
            desc = desc[:400] + "…"
        return {
            "entity_id": raw.get("entity_id"),
            "name": raw.get("name"),
            "entity_type": raw.get("entity_type"),
            "entity_subtype": raw.get("entity_subtype"),
            "description": desc,
            "namespace": raw.get("namespace"),
        }

    @staticmethod
    def _entity_brief(raw: JsonObject) -> JsonObject:
        return require_json_object(raw, "crm.entity")

    @staticmethod
    def _suggest_brief(raw: JsonObject) -> JsonObject:
        suggest_id = raw.get("suggest_id")
        if not isinstance(suggest_id, str) or not suggest_id.strip():
            raise ValueError("suggest response missing suggest_id")
        return {
            "suggest_id": suggest_id,
            "suggest_type": raw.get("suggest_type"),
            "status": raw.get("status"),
            "target_entity_ids": raw.get("target_entity_ids"),
            "payload": raw.get("payload"),
        }

    @staticmethod
    def _require_entity_id(entity_id: str | CrmGetEntityArgs | CrmDeleteEntityArgs) -> str:
        if isinstance(entity_id, (CrmGetEntityArgs, CrmDeleteEntityArgs)):
            value = entity_id.entity_id.strip()
        else:
            value = entity_id.strip()
        if not value:
            raise ValueError("entity_id is required")
        return value

    async def search_entities(
        self,
        query: str | CrmSearchEntitiesArgs,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        limit: int = 100,
    ) -> JsonObject:
        if isinstance(query, CrmSearchEntitiesArgs):
            args = query
        else:
            args = CrmSearchEntitiesArgs(
                query=query,
                entity_type=entity_type,
                entity_subtype=entity_subtype,
                namespace=namespace,
                limit=limit,
            )
        q = args.query.strip()
        if not q:
            raise ValueError(
                (
                    "Нужен непустой параметр query — короткая строка семантического поиска "
                    "(ключевые слова из запроса пользователя)."
                )
            )
        ns = self._resolve_namespace(args.namespace)
        payload: JsonObject = {
            "query": q,
            "namespace": ns,
            "search_mode": "hybrid",
            "limit": max(1, min(1000, int(args.limit))),
        }
        if args.entity_type is not None:
            payload["entity_type"] = args.entity_type
        if args.entity_subtype is not None:
            payload["entity_subtype"] = args.entity_subtype

        raw_response = await self._http.post(
            "crm",
            f"{_API}/entities/query",
            json=payload,
            headers=self._ns_headers(),
        )
        page = require_json_object(raw_response, "crm.search_entities")
        hits = [
            self._compact_entity_hit(item)
            for item in self._as_objects(page.get("items"), "crm.search_entities.items")
        ]
        summary = f"Найдено сущностей: {len(hits)}."
        blocks: list[JsonObject] = [{"type": "text", "text": summary}]
        if hits:
            rows: list[JsonObject] = [
                {
                    "entity_id": hit.get("entity_id"),
                    "name": hit.get("name"),
                    "type": hit.get("entity_type"),
                    "subtype": hit.get("entity_subtype"),
                }
                for hit in hits[:20]
            ]
            blocks.append(
                {
                    "type": "table",
                    "title": "Результаты поиска",
                    "columns": [
                        {"key": "name", "label": "Имя"},
                        {"key": "type", "label": "Тип"},
                        {"key": "entity_id", "label": "ID"},
                    ],
                    "rows": rows,
                }
            )
        return {"hits": hits, "blocks": blocks}

    async def create_note(
        self,
        name: str | CrmCapabilityCreateNoteArgs,
        description: str = "",
        note_date: str | None = None,
        namespace: str | None = None,
    ) -> JsonObject:
        if isinstance(name, CrmCapabilityCreateNoteArgs):
            args = name
        else:
            args = CrmCapabilityCreateNoteArgs(
                name=name,
                description=description,
                note_date=note_date,
                namespace=namespace,
            )
        ns = self._resolve_namespace(args.namespace)
        body: JsonObject = {
            "entity_type": "note",
            "namespace": ns,
            "name": args.name.strip(),
            "description": args.description,
        }
        if args.note_date is not None and str(args.note_date).strip():
            body["note_date"] = str(args.note_date).strip()
        raw = await self._http.post(
            "crm",
            f"{_API}/entities",
            json=body,
            headers=self._ns_headers(),
        )
        entity = self._entity_brief(require_json_object(raw, "crm.create_note"))
        entity_id = entity.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError("crm.create_note: response missing entity_id")
        return {
            "entity_id": entity_id,
            "entity": entity,
            "blocks": [
                {
                    "type": "card",
                    "title": entity.get("name") or "Note",
                    "subtitle": entity_id,
                }
            ],
        }

    async def analyze_note_text(
        self,
        note_id: str | CrmAnalyzeNoteTextArgs,
        extract_entity_types: list[str] | None = None,
        mentioned_entity_ids: list[str] | None = None,
    ) -> JsonObject:
        if isinstance(note_id, CrmAnalyzeNoteTextArgs):
            args = note_id
        else:
            args = CrmAnalyzeNoteTextArgs(
                note_id=note_id,
                extract_entity_types=extract_entity_types,
                mentioned_entity_ids=mentioned_entity_ids,
            )
        nid = args.note_id.strip()
        body: JsonObject = {
            "note_id": nid,
            "mode": "analyze",
            "include_attachments": True,
            "check_duplicates": True,
        }
        if args.extract_entity_types is not None:
            body["extract_entity_types"] = list(args.extract_entity_types)
        if args.mentioned_entity_ids is not None:
            body["mentioned_entity_ids"] = list(args.mentioned_entity_ids)
        start_raw = await self._http.post(
            "crm",
            f"{_API}/tasks/note-analyze",
            json=body,
            headers=self._ns_headers(),
            timeout=60.0,
        )
        start = require_json_object(start_raw, "crm.note_analyze.start")
        task_id = start.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("crm.note_analyze: start response missing task_id")
        return await self._poll_note_analyze_task(
            task_id=task_id.strip(),
            note_id=nid,
            mode="analyze",
        )

    async def create_note_and_analyze(
        self,
        name: str | CrmCreateNoteAndAnalyzeArgs,
        description: str = "",
        note_date: str | None = None,
        extract_entity_types: list[str] | None = None,
        mentioned_entity_ids: list[str] | None = None,
        namespace: str | None = None,
    ) -> JsonObject:
        if isinstance(name, CrmCreateNoteAndAnalyzeArgs):
            args = name
        else:
            args = CrmCreateNoteAndAnalyzeArgs(
                name=name,
                description=description,
                note_date=note_date,
                extract_entity_types=extract_entity_types,
                mentioned_entity_ids=mentioned_entity_ids,
                namespace=namespace,
            )
        created = await self.create_note(
            name=args.name,
            description=args.description,
            note_date=args.note_date,
            namespace=args.namespace,
        )
        entity_id = created.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError("crm.create_note_and_analyze: missing entity_id after create")
        analyzed = await self.analyze_note_text(
            note_id=entity_id,
            extract_entity_types=args.extract_entity_types,
            mentioned_entity_ids=args.mentioned_entity_ids,
        )
        blocks_out: list[JsonObject] = []
        analyzed_blocks = analyzed.get("blocks")
        if isinstance(analyzed_blocks, list):
            for index, block in enumerate(analyzed_blocks):
                blocks_out.append(
                    require_json_object(block, f"crm.create_note_and_analyze.blocks[{index}]")
                )
        return {
            "entity_id": entity_id,
            "entity": created.get("entity"),
            "analyze": analyzed.get("analyze"),
            "blocks": blocks_out,
        }

    async def get_entity(self, entity_id: str | CrmGetEntityArgs) -> JsonObject:
        eid = self._require_entity_id(entity_id)
        raw = await self._http.get(
            "crm",
            f"{_API}/entities/{quote(eid, safe='')}",
            headers=self._ns_headers(),
        )
        entity = self._entity_brief(require_json_object(raw, "crm.get_entity"))
        blocks: list[JsonObject] = [
            {
                "type": "card",
                "title": entity.get("name") or eid,
                "subtitle": entity.get("entity_type"),
            }
        ]
        return {"entity": entity, "blocks": blocks}

    async def create_entity(
        self,
        entity_type: str | CrmCreateEntityArgs,
        name: str = "",
        entity_subtype: str | None = None,
        namespace: str | None = None,
        description: str | None = None,
        attributes: JsonObject | None = None,
        tags: list[str] | None = None,
    ) -> JsonObject:
        if isinstance(entity_type, CrmCreateEntityArgs):
            args = entity_type
        else:
            args = CrmCreateEntityArgs(
                entity_type=entity_type,
                name=name,
                entity_subtype=entity_subtype,
                namespace=namespace,
                description=description,
                attributes=attributes,
                tags=tags,
            )
        ns = self._resolve_namespace(args.namespace)
        body: JsonObject = {
            "entity_type": args.entity_type.strip(),
            "name": args.name.strip(),
            "namespace": ns,
        }
        if args.entity_subtype is not None and args.entity_subtype.strip():
            body["entity_subtype"] = args.entity_subtype.strip()
        if args.description is not None and args.description.strip():
            body["description"] = args.description.strip()
        if args.attributes is not None:
            body["attributes"] = args.attributes
        if args.tags is not None:
            body["tags"] = list(args.tags)
        raw = await self._http.post(
            "crm",
            f"{_API}/entities",
            json=body,
            headers=self._ns_headers(),
        )
        entity = self._entity_brief(require_json_object(raw, "crm.create_entity"))
        entity_id = entity.get("entity_id")
        blocks: list[JsonObject] = [
            {
                "type": "card",
                "title": entity.get("name") or "Entity",
                "subtitle": entity_id,
            }
        ]
        return {"entity": entity, "blocks": blocks}

    async def create_relationship(
        self,
        source_entity_id: str | CrmCreateRelationshipArgs,
        target_entity_id: str = "",
        relationship_type: str = "",
        namespace: str | None = None,
        weight: float = 1.0,
        confidence: float = 1.0,
    ) -> JsonObject:
        if isinstance(source_entity_id, CrmCreateRelationshipArgs):
            args = source_entity_id
        else:
            args = CrmCreateRelationshipArgs(
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relationship_type=relationship_type,
                namespace=namespace,
                weight=weight,
                confidence=confidence,
            )
        ns = self._resolve_namespace(args.namespace)
        body: JsonObject = {
            "source_entity_id": args.source_entity_id.strip(),
            "target_entity_id": args.target_entity_id.strip(),
            "relationship_type": args.relationship_type.strip(),
            "namespace": ns,
            "weight": args.weight,
            "confidence": args.confidence,
        }
        raw = await self._http.post(
            "crm",
            f"{_API}/relationships",
            json=body,
            headers=self._ns_headers(),
        )
        relationship = require_json_object(raw, "crm.create_relationship")
        rid = relationship.get("relationship_id")
        txt = (
            f"Связь {args.relationship_type.strip()} создана ({rid}): "
            f"{relationship.get('source_entity_id')} → {relationship.get('target_entity_id')}."
        )
        return {
            "relationship": relationship,
            "blocks": [{"type": "text", "text": txt}],
        }

    async def list_entity_types(
        self,
        namespace: str | None | CrmListEntityTypesArgs = None,
    ) -> JsonObject:
        if isinstance(namespace, CrmListEntityTypesArgs):
            args = namespace
        else:
            args = CrmListEntityTypesArgs(namespace=namespace)
        ns = self._resolve_namespace(args.namespace)
        path = f"{_API}/entity-types?namespace={quote(ns, safe='')}"
        raw = await self._http.get("crm", path, headers=self._ns_headers())
        page = require_json_object(raw, "crm.list_entity_types")
        items_raw = self._as_objects(page.get("items"), "crm.list_entity_types.items")
        compact: list[JsonObject] = [
            {
                "type_id": item.get("type_id"),
                "name": item.get("name"),
                "parent_type_id": item.get("parent_type_id"),
            }
            for item in items_raw
        ]
        lines = compact[:80]
        blocks: list[JsonObject] = [
            {
                "type": "table",
                "title": "Типы сущностей",
                "columns": [
                    {"key": "type_id", "label": "type_id"},
                    {"key": "name", "label": "Имя"},
                    {"key": "parent_type_id", "label": "Родитель"},
                ],
                "rows": lines,
            }
        ]
        return {
            "namespace": ns,
            "count": len(compact),
            "items": compact,
            "blocks": blocks,
        }

    async def daily_summary(
        self,
        date: str | CrmDailySummaryArgs,
        namespace: str | None = None,
        force_rebuild: bool = False,
    ) -> JsonObject:
        if isinstance(date, CrmDailySummaryArgs):
            args = date
        else:
            args = CrmDailySummaryArgs(date=date, namespace=namespace, force_rebuild=force_rebuild)
        d_raw = args.date.strip()
        if not d_raw:
            raise ValueError("date is required")
        body: JsonObject = {"date": d_raw, "force_rebuild": bool(args.force_rebuild)}
        if args.namespace is not None and args.namespace.strip():
            body["namespace"] = args.namespace.strip()
        raw = await self._http.post(
            "crm",
            f"{_API}/entities/daily-summary",
            json=body,
            headers=self._ns_headers(),
        )
        response = require_json_object(raw, "crm.daily_summary")
        summary_text = response.get("summary")
        if isinstance(summary_text, str) and summary_text.strip():
            main = summary_text.strip()
        else:
            main = json.dumps(response, ensure_ascii=False)[:2500]
        return {"response": response, "blocks": [{"type": "text", "text": main}]}

    async def update_entity(
        self,
        entity_id: str | CrmUpdateEntityArgs,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        tags: list[str] | None = None,
        note_date: str | None = None,
    ) -> JsonObject:
        if isinstance(entity_id, CrmUpdateEntityArgs):
            args = entity_id
        else:
            args = CrmUpdateEntityArgs(
                entity_id=entity_id,
                name=name,
                description=description,
                status=status,
                entity_type=entity_type,
                entity_subtype=entity_subtype,
                tags=tags,
                note_date=note_date,
            )
        eid = args.entity_id.strip()
        if not eid:
            raise ValueError("entity_id is required")
        body: JsonObject = {}
        if args.name is not None and args.name.strip():
            body["name"] = args.name.strip()
        if args.description is not None:
            body["description"] = args.description
        if args.status is not None and args.status.strip():
            body["status"] = args.status.strip()
        if args.entity_type is not None and args.entity_type.strip():
            body["entity_type"] = args.entity_type.strip()
        if args.entity_subtype is not None and args.entity_subtype.strip():
            body["entity_subtype"] = args.entity_subtype.strip()
        if args.tags is not None:
            body["tags"] = list(args.tags)
        if args.note_date is not None and args.note_date.strip():
            _ = Date.fromisoformat(args.note_date.strip())
            body["note_date"] = args.note_date.strip()
        if not body:
            raise ValueError("crm_update_entity: at least one field to update is required")
        raw = await self._http.put(
            "crm",
            f"{_API}/entities/{quote(eid, safe='')}",
            json=body,
            headers=self._ns_headers(),
        )
        entity = self._entity_brief(require_json_object(raw, "crm.update_entity"))
        return {"entity": entity}

    async def delete_entity(self, entity_id: str | CrmDeleteEntityArgs) -> JsonObject:
        eid = self._require_entity_id(entity_id)
        raw = await self._http.delete(
            "crm",
            f"{_API}/entities/{quote(eid, safe='')}",
            headers=self._ns_headers(),
        )
        if isinstance(raw, dict):
            return {"entity_id": eid, **require_json_object(raw, "crm.delete_entity")}
        return {"entity_id": eid}

    async def list_notes(
        self,
        date_from: str | CrmListNotesArgs,
        date_to: str | None = None,
        namespace: str | None = None,
        query: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> JsonObject:
        if isinstance(date_from, CrmListNotesArgs):
            args = date_from
        else:
            args = CrmListNotesArgs(
                date_from=date_from,
                date_to=date_to,
                namespace=namespace,
                query=query,
                limit=limit,
                cursor=cursor,
            )
        start = args.date_from.strip()
        end = args.date_to.strip() if args.date_to and args.date_to.strip() else start
        _ = Date.fromisoformat(start)
        _ = Date.fromisoformat(end)
        ns = self._resolve_namespace(args.namespace)
        if start == end:
            filters: JsonObject = {"field": "note_date", "op": "$eq", "value": start}
        else:
            filters = {
                "$and": [
                    {"field": "note_date", "op": "$gte", "value": start},
                    {"field": "note_date", "op": "$lte", "value": end},
                ]
            }
        body: JsonObject = {
            "entity_type": "note",
            "namespace": ns,
            "filters": filters,
            "limit": args.limit,
            "search_mode": "text"
            if not (args.query and args.query.strip())
            else "hybrid",
        }
        if args.query is not None and args.query.strip():
            body["query"] = args.query.strip()
        if args.cursor is not None and args.cursor.strip():
            body["cursor"] = args.cursor.strip()
        raw = await self._http.post(
            "crm",
            f"{_API}/entities/query",
            json=body,
            headers=self._ns_headers(),
        )
        page = require_json_object(raw, "crm.list_notes")
        items: list[JsonObject] = []
        for item in self._as_objects(page.get("items"), "crm.list_notes.items"):
            note_date = item.get("note_date")
            items.append(
                {
                    "entity_id": item.get("entity_id"),
                    "name": item.get("name"),
                    "note_date": note_date,
                    "entity_subtype": item.get("entity_subtype"),
                    "namespace": item.get("namespace"),
                    "status": item.get("status"),
                }
            )
        return {
            "items": items,
            "next_cursor": page.get("next_cursor"),
            "has_more": page.get("has_more"),
            "count": len(items),
            "date_from": start,
            "date_to": end,
            "namespace": ns,
        }

    async def apply_analysis_draft(
        self,
        note_id: str | CrmApplyAnalysisDraftArgs,
    ) -> JsonObject:
        if isinstance(note_id, CrmApplyAnalysisDraftArgs):
            nid = note_id.note_id.strip()
        else:
            nid = note_id.strip()
        if not nid:
            raise ValueError("note_id is required")
        body: JsonObject = {"note_id": nid, "mode": "apply"}
        start_raw = await self._http.post(
            "crm",
            f"{_API}/tasks/note-analyze",
            json=body,
            headers=self._ns_headers(),
            timeout=60.0,
        )
        start = require_json_object(start_raw, "crm.apply_analysis_draft.start")
        task_id = start.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("crm.apply_analysis_draft: start response missing task_id")
        return await self._poll_note_analyze_task(
            task_id=task_id.strip(),
            note_id=nid,
            mode="apply",
        )

    async def discard_analysis_draft(
        self,
        note_id: str | CrmDiscardAnalysisDraftArgs,
    ) -> JsonObject:
        if isinstance(note_id, CrmDiscardAnalysisDraftArgs):
            nid = note_id.note_id.strip()
        else:
            nid = note_id.strip()
        if not nid:
            raise ValueError("note_id is required")
        _ = await self._http.delete(
            "crm",
            f"{_API}/entities/notes/{quote(nid, safe='')}/analysis-draft",
            headers=self._ns_headers(),
        )
        return {"note_id": nid, "status": "draft_discarded"}

    async def merge_entities(
        self,
        survivor_entity_id: str | CrmMergeEntitiesArgs,
        source_entity_id: str = "",
    ) -> JsonObject:
        if isinstance(survivor_entity_id, CrmMergeEntitiesArgs):
            args = survivor_entity_id
        else:
            args = CrmMergeEntitiesArgs(
                survivor_entity_id=survivor_entity_id,
                source_entity_id=source_entity_id,
            )
        survivor = args.survivor_entity_id.strip()
        source = args.source_entity_id.strip()
        if not survivor or not source:
            raise ValueError("survivor_entity_id and source_entity_id are required")
        if survivor == source:
            raise ValueError("survivor_entity_id and source_entity_id must differ")
        body: JsonObject = {
            "survivor_entity_id": survivor,
            "source_entity_id": source,
        }
        raw = await self._http.post(
            "crm",
            f"{_API}/entities/merge",
            json=body,
            headers=self._ns_headers(),
        )
        merge = require_json_object(raw, "crm.merge_entities")
        return {"merge": merge}

    async def period_summary(
        self,
        date_from: str | CrmPeriodSummaryArgs,
        date_to: str = "",
        namespace: str | None = None,
        force_rebuild: bool = False,
    ) -> JsonObject:
        if isinstance(date_from, CrmPeriodSummaryArgs):
            args = date_from
        else:
            args = CrmPeriodSummaryArgs(
                date_from=date_from,
                date_to=date_to,
                namespace=namespace,
                force_rebuild=force_rebuild,
            )
        start = args.date_from.strip()
        end = args.date_to.strip()
        if not start or not end:
            raise ValueError("date_from and date_to are required")
        body: JsonObject = {
            "date_from": start,
            "date_to": end,
            "force_rebuild": bool(args.force_rebuild),
        }
        if args.namespace is not None and args.namespace.strip():
            body["namespace"] = args.namespace.strip()
        raw = await self._http.post(
            "crm",
            f"{_API}/entities/period-summary",
            json=body,
            headers=self._ns_headers(),
        )
        response = require_json_object(raw, "crm.period_summary")
        summary_text = response.get("summary")
        if isinstance(summary_text, str) and summary_text.strip():
            main = summary_text.strip()
        else:
            main = json.dumps(response, ensure_ascii=False)[:2500]
        return {"response": response, "blocks": [{"type": "text", "text": main}]}

    async def create_activity_task(
        self,
        title: str | CrmCreateActivityTaskArgs,
        description: str | None = None,
        namespace: str | None = None,
        entity_subtype: str | None = None,
        priority: str | None = None,
        due_date: str | None = None,
        assignees: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> JsonObject:
        if isinstance(title, CrmCreateActivityTaskArgs):
            args = title
        else:
            args = CrmCreateActivityTaskArgs(
                title=title,
                description=description,
                namespace=namespace,
                entity_subtype=entity_subtype,
                priority=priority,
                due_date=due_date,
                assignees=assignees,
                tags=tags,
            )
        ns = self._resolve_namespace(args.namespace)
        body: JsonObject = {"title": args.title.strip(), "namespace": ns}
        if args.description is not None and args.description.strip():
            body["description"] = args.description.strip()
        if args.entity_subtype is not None and args.entity_subtype.strip():
            body["entity_subtype"] = args.entity_subtype.strip()
        if args.priority is not None and args.priority.strip():
            body["priority"] = args.priority.strip()
        if args.due_date is not None and args.due_date.strip():
            body["due_date"] = args.due_date.strip()
        if args.assignees is not None:
            body["assignees"] = list(args.assignees)
        if args.tags is not None:
            body["tags"] = list(args.tags)
        raw = await self._http.post(
            "crm",
            f"{_API}/activity-tasks",
            json=body,
            headers=self._ns_headers(),
        )
        payload = require_json_object(raw, "crm.create_activity_task")
        entity_raw = payload.get("entity")
        work_raw = payload.get("work_item")
        if not isinstance(entity_raw, dict) or not isinstance(work_raw, dict):
            raise ValueError("crm_create_activity_task: invalid response shape")
        entity = require_json_object(entity_raw, "crm.activity.entity")
        work_item = require_json_object(work_raw, "crm.activity.work_item")
        entity_id = entity.get("entity_id")
        work_item_id = work_item.get("work_item_id")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError("crm_create_activity_task: missing entity_id")
        if not isinstance(work_item_id, str) or not work_item_id.strip():
            raise ValueError("crm_create_activity_task: missing work_item_id")
        return {
            "entity_id": entity_id,
            "work_item_id": work_item_id,
            "entity": entity,
            "work_item": work_item,
            "blocks": [
                {
                    "type": "card",
                    "title": entity.get("name"),
                    "subtitle": f"work_item_id={work_item_id}",
                }
            ],
        }

    async def list_activity_tasks(
        self,
        namespace: str | None | CrmListActivityTasksArgs = None,
        work_item_state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> JsonObject:
        if isinstance(namespace, CrmListActivityTasksArgs):
            args = namespace
        else:
            args = CrmListActivityTasksArgs(
                namespace=namespace,
                work_item_state=work_item_state,
                limit=limit,
                offset=offset,
            )
        query: dict[str, str] = {
            "limit": str(args.limit),
            "offset": str(args.offset),
        }
        if args.namespace is not None and args.namespace.strip():
            query["namespace"] = args.namespace.strip()
        if args.work_item_state is not None and args.work_item_state.strip():
            query["state"] = args.work_item_state.strip()
        path = f"{_API}/activity-tasks?{urlencode(query)}"
        raw = await self._http.get("crm", path, headers=self._ns_headers())
        page = require_json_object(raw, "crm.list_activity_tasks")
        items: list[JsonObject] = []
        for item in self._as_objects(page.get("items"), "crm.list_activity_tasks.items"):
            state_value = item.get("state")
            kind_value = item.get("kind")
            items.append(
                {
                    "work_item_id": item.get("work_item_id"),
                    "title": item.get("title"),
                    "state": state_value,
                    "kind": kind_value,
                    "namespace": item.get("namespace"),
                }
            )
        return {
            "items": items,
            "total": page.get("total"),
            "limit": page.get("limit"),
            "offset": page.get("offset"),
            "count": len(items),
        }

    async def list_relationships(
        self,
        entity_id: str | None | CrmListRelationshipsArgs = None,
        namespace: str | None = None,
        limit: int = 200,
        cursor: str | None = None,
    ) -> JsonObject:
        if isinstance(entity_id, CrmListRelationshipsArgs):
            args = entity_id
        else:
            args = CrmListRelationshipsArgs(
                entity_id=entity_id,
                namespace=namespace,
                limit=limit,
                cursor=cursor,
            )
        ns = self._resolve_namespace(args.namespace)
        query: dict[str, str] = {"namespace": ns, "limit": str(args.limit)}
        if args.entity_id is not None and args.entity_id.strip():
            query["entity_id"] = args.entity_id.strip()
        if args.cursor is not None and args.cursor.strip():
            query["cursor"] = args.cursor.strip()
        path = f"{_API}/relationships?{urlencode(query)}"
        raw = await self._http.get("crm", path, headers=self._ns_headers())
        page = require_json_object(raw, "crm.list_relationships")
        items = self._as_objects(page.get("items"), "crm.list_relationships.items")
        return {
            "items": items,
            "next_cursor": page.get("next_cursor"),
            "has_more": page.get("has_more"),
            "count": len(items),
        }

    async def delete_relationship(
        self,
        relationship_id: str | CrmDeleteRelationshipArgs,
    ) -> JsonObject:
        if isinstance(relationship_id, CrmDeleteRelationshipArgs):
            rid = relationship_id.relationship_id.strip()
        else:
            rid = relationship_id.strip()
        if not rid:
            raise ValueError("relationship_id is required")
        _ = await self._http.delete(
            "crm",
            f"{_API}/relationships/{quote(rid, safe='')}",
            headers=self._ns_headers(),
        )
        return {"relationship_id": rid, "status": "deleted"}

    async def list_relationship_types(
        self,
        limit: int | CrmListRelationshipTypesArgs = 200,
        offset: int = 0,
    ) -> JsonObject:
        if isinstance(limit, CrmListRelationshipTypesArgs):
            args = limit
        else:
            args = CrmListRelationshipTypesArgs(limit=limit, offset=offset)
        path = f"{_API}/relationships/types/?limit={args.limit}&offset={args.offset}"
        raw = await self._http.get("crm", path, headers=self._ns_headers())
        page = require_json_object(raw, "crm.list_relationship_types")
        compact: list[JsonObject] = []
        for item in self._as_objects(page.get("items"), "crm.list_relationship_types.items"):
            compact.append(
                {
                    "type_id": item.get("type_id"),
                    "name": item.get("name"),
                    "is_directed": item.get("is_directed"),
                    "inverse_type_id": item.get("inverse_type_id"),
                }
            )
        return {
            "items": compact,
            "total": page.get("total"),
            "limit": page.get("limit"),
            "offset": page.get("offset"),
            "count": len(compact),
        }

    async def entity_related(
        self,
        entity_id: str | CrmEntityRelatedArgs,
        direction: Literal["incoming", "outgoing", "both"] = "both",
        relationship_type: str | None = None,
        namespace: str | None = None,
    ) -> JsonObject:
        if isinstance(entity_id, CrmEntityRelatedArgs):
            args = entity_id
        else:
            args = CrmEntityRelatedArgs(
                entity_id=entity_id,
                direction=direction,
                relationship_type=relationship_type,
                namespace=namespace,
            )
        eid = args.entity_id.strip()
        if not eid:
            raise ValueError("entity_id is required")
        ns = self._resolve_namespace(args.namespace)
        query: dict[str, str] = {"direction": args.direction, "namespace": ns}
        if args.relationship_type is not None and args.relationship_type.strip():
            query["relationship_type"] = args.relationship_type.strip()
        path = f"{_API}/entities/{quote(eid, safe='')}/related?{urlencode(query)}"
        raw = await self._http.get("crm", path, headers=self._ns_headers())
        related = require_json_object(raw, "crm.entity_related")
        return {"related": related}

    async def shortest_path(
        self,
        from_entity_id: str | CrmShortestPathArgs,
        to_entity_id: str = "",
        max_depth: int = 10,
        namespace: str | None = None,
    ) -> JsonObject:
        if isinstance(from_entity_id, CrmShortestPathArgs):
            args = from_entity_id
        else:
            args = CrmShortestPathArgs(
                from_entity_id=from_entity_id,
                to_entity_id=to_entity_id,
                max_depth=max_depth,
                namespace=namespace,
            )
        src = args.from_entity_id.strip()
        dst = args.to_entity_id.strip()
        if not src or not dst:
            raise ValueError("from_entity_id and to_entity_id are required")
        ns = self._resolve_namespace(args.namespace)
        query = {
            "source_entity_id": src,
            "target_entity_id": dst,
            "max_depth": str(args.max_depth),
            "namespace": ns,
        }
        path = f"{_API}/relationships/path/?{urlencode(query)}"
        raw = await self._http.get("crm", path, headers=self._ns_headers())
        result = require_json_object(raw, "crm.shortest_path")
        return {"path": result}

    async def list_suggests(
        self,
        namespace: str | None | CrmListSuggestsArgs = None,
        status: str = "pending",
        limit: int = 50,
        offset: int = 0,
    ) -> JsonObject:
        if isinstance(namespace, CrmListSuggestsArgs):
            args = namespace
        else:
            args = CrmListSuggestsArgs(
                namespace=namespace,
                status=status,
                limit=limit,
                offset=offset,
            )
        ns = self._resolve_namespace(args.namespace)
        query = urlencode(
            {"status": args.status, "limit": str(args.limit), "offset": str(args.offset)}
        )
        path = f"{_API}/namespaces/{quote(ns, safe='')}/suggests?{query}"
        raw = await self._http.get("crm", path, headers=self._ns_headers())
        page_obj = require_json_object(raw, "crm.list_suggests")
        items_raw = page_obj.get("items")
        if not isinstance(items_raw, list):
            raise ValueError("crm_list_suggests: items missing")
        items: list[JsonObject] = []
        for index, item in enumerate(items_raw):
            if isinstance(item, dict):
                items.append(
                    self._suggest_brief(
                        require_json_object(item, f"crm.list_suggests.item[{index}]")
                    )
                )
        return {
            "namespace": ns,
            "items": items,
            "total": page_obj.get("total"),
            "limit": page_obj.get("limit"),
            "offset": page_obj.get("offset"),
            "count": len(items),
        }

    async def resolve_suggest(
        self,
        suggest_id: str | CrmSuggestIdArgs,
        namespace: str | None = None,
    ) -> JsonObject:
        if isinstance(suggest_id, CrmSuggestIdArgs):
            args = suggest_id
        else:
            args = CrmSuggestIdArgs(suggest_id=suggest_id, namespace=namespace)
        sid = args.suggest_id.strip()
        if not sid:
            raise ValueError("suggest_id is required")
        ns = self._resolve_namespace(args.namespace)
        path = (
            f"{_API}/namespaces/{quote(ns, safe='')}/suggests/"
            f"{quote(sid, safe='')}/resolve"
        )
        raw = await self._http.post("crm", path, headers=self._ns_headers())
        brief = self._suggest_brief(require_json_object(raw, "crm.resolve_suggest"))
        return {"suggest": brief}

    async def dismiss_suggest(
        self,
        suggest_id: str | CrmSuggestIdArgs,
        namespace: str | None = None,
    ) -> JsonObject:
        if isinstance(suggest_id, CrmSuggestIdArgs):
            args = suggest_id
        else:
            args = CrmSuggestIdArgs(suggest_id=suggest_id, namespace=namespace)
        sid = args.suggest_id.strip()
        if not sid:
            raise ValueError("suggest_id is required")
        ns = self._resolve_namespace(args.namespace)
        path = (
            f"{_API}/namespaces/{quote(ns, safe='')}/suggests/"
            f"{quote(sid, safe='')}/dismiss"
        )
        raw = await self._http.post("crm", path, headers=self._ns_headers())
        brief = self._suggest_brief(require_json_object(raw, "crm.dismiss_suggest"))
        return {"suggest": brief}

    async def knowledge_import_status(
        self,
        namespace: str | None | CrmKnowledgeImportStatusArgs = None,
        limit: int = 50,
        offset: int = 0,
    ) -> JsonObject:
        if isinstance(namespace, CrmKnowledgeImportStatusArgs):
            args = namespace
        else:
            args = CrmKnowledgeImportStatusArgs(
                namespace=namespace,
                limit=limit,
                offset=offset,
            )
        ns = self._resolve_namespace(args.namespace)
        query = urlencode(
            {
                "namespace": ns,
                "task_type": "knowledge_import",
                "limit": str(args.limit),
                "offset": str(args.offset),
            }
        )
        raw = await self._http.get(
            "crm",
            f"{_API}/tasks?{query}",
            headers=self._ns_headers(),
        )
        page = require_json_object(raw, "crm.knowledge_import_status")
        items: list[JsonObject] = []
        for task in self._as_objects(page.get("items"), "crm.knowledge_import_status.items"):
            data: JsonValue = task.get("data")
            items.append(
                {
                    "task_id": task.get("task_id"),
                    "status": task.get("status"),
                    "stage": task.get("stage"),
                    "progress_pct": task.get("progress_pct"),
                    "error_message": task.get("error_message"),
                    "namespace": task.get("namespace"),
                    "data": data,
                }
            )
        return {
            "namespace": ns,
            "items": items,
            "total": page.get("total"),
            "limit": page.get("limit"),
            "offset": page.get("offset"),
            "count": len(items),
        }

    async def _poll_note_analyze_task(
        self,
        *,
        task_id: str,
        note_id: str,
        mode: Literal["analyze", "apply"],
    ) -> JsonObject:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _NOTE_ANALYZE_POLL_SEC
        terminal = require_json_object(
            await self._http.get(
                "crm",
                f"{_API}/tasks/{quote(task_id, safe='')}",
                headers=self._ns_headers(),
                timeout=30.0,
            ),
            "crm.note_analyze.task",
        )
        while True:
            status = terminal.get("status")
            if status in ("completed", "failed", "cancelled"):
                break
            if loop.time() >= deadline:
                raise TimeoutError(
                    f"crm note-analyze ({mode}) timed out task_id={task_id} last={terminal!r}"
                )
            await asyncio.sleep(_NOTE_ANALYZE_SLEEP_SEC)
            terminal = require_json_object(
                await self._http.get(
                    "crm",
                    f"{_API}/tasks/{quote(task_id, safe='')}",
                    headers=self._ns_headers(),
                    timeout=30.0,
                ),
                "crm.note_analyze.task",
            )

        status = terminal.get("status")
        if status != "completed":
            error_message = terminal.get("error_message")
            detail = (
                error_message
                if isinstance(error_message, str) and error_message.strip()
                else f"note-analyze {mode} {status}"
            )
            raise RuntimeError(detail)

        if mode == "apply":
            return {
                "note_id": note_id,
                "task_id": task_id,
                "mode": "apply",
                "task": terminal,
                "blocks": [
                    {
                        "type": "text",
                        "text": "Черновик анализа применён к графу.",
                    }
                ],
            }

        entity_raw = await self._http.get(
            "crm",
            f"{_API}/entities/{quote(note_id, safe='')}",
            headers=self._ns_headers(),
            timeout=60.0,
        )
        entity = require_json_object(entity_raw, "crm.note_analyze.entity")
        attributes = entity.get("attributes")
        draft_payload: JsonObject = {}
        if isinstance(attributes, dict):
            raw_draft = attributes.get("ai_analysis_draft")
            if isinstance(raw_draft, dict):
                draft_payload = require_json_object(raw_draft, "crm.note_analyze.draft")

        summary = "Анализ выполнен."
        entities_list = draft_payload.get("entities")
        task_data = terminal.get("data")
        data_obj = task_data if isinstance(task_data, dict) else {}
        if isinstance(entities_list, list) and len(entities_list) > 0:
            summary = f"Найдено сущностей: {len(entities_list)}."
        else:
            cnt = data_obj.get("result_entities_count")
            if isinstance(cnt, int) and cnt > 0:
                summary = f"Найдено сущностей: {cnt}."

        analyze_payload: JsonObject = {"task_id": task_id, **draft_payload}
        if "result_entities_count" not in analyze_payload and "result_entities_count" in data_obj:
            analyze_payload["result_entities_count"] = data_obj["result_entities_count"]
        if (
            "result_relationships_count" not in analyze_payload
            and "result_relationships_count" in data_obj
        ):
            analyze_payload["result_relationships_count"] = data_obj["result_relationships_count"]

        blocks: list[JsonObject] = [
            {"type": "text", "text": summary},
            {
                "type": "actions",
                "buttons": [
                    {
                        "action_id": "crm.entity.open",
                        "action_kind": "open_entity",
                        "label": "Открыть заметку",
                        "arguments": {"entity_id": note_id},
                        "context": {"entity_id": note_id, "entity_type": "note"},
                    }
                ],
            },
        ]
        return {"analyze": analyze_payload, "blocks": blocks}
