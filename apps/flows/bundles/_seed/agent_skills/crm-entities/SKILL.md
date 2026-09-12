---
name: crm-entities
description: Search, create, update, delete, merge CRM NetWorkle entities; types; daily/period summaries; activity-task bridge; embed blocks.
allowed-tools: crm_search_entities crm_create_entity crm_get_entity crm_update_entity crm_delete_entity crm_merge_entities crm_create_relationship crm_list_entity_types crm_daily_summary crm_period_summary crm_create_activity_task crm_list_activity_tasks ui_render
---

# CRM entities

## Goal

Work with NetWorkle CRM graph entities (CRUD, merge, relationships create, types, summaries) and create CRM activity tasks (pair with WorkItem).

## Procedure

1. Discover types — `crm_list_entity_types` when the user is unsure about `entity_type` / `entity_subtype`.
2. Search — `crm_search_entities`; set type filters only if the user asked; namespace from session.
3. Details — `crm_get_entity` with a real `entity_id`.
4. Create — `crm_create_entity` only with fields the user provided; never invent ids.
5. Update — `crm_update_entity` with real `entity_id` and only changed fields.
6. Delete — `crm_delete_entity` only after explicit user confirmation.
7. Merge — `crm_merge_entities` with real survivor/source ids (survivor keeps `entity_id`).
8. Relationships create — `crm_create_relationship`; list/delete/neighborhood — load parent `crm-graph`.
9. Digests — `crm_daily_summary` / `crm_period_summary`.
10. Activity task — `crm_create_activity_task` / `crm_list_activity_tasks`; then load `work-items` for state/board/assignee.
11. Structured UI — `ui_render` (slot_id `conversation`) when a visual summary helps.

## Rules

- Never invent `entity_id` / `work_item_id`.
- Work fields (priority/due/assignee/state/board) after create — only via Worktracker tools.
- After a successful tool call, briefly summarize; do not dump raw JSON.
