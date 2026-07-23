---
name: networkle
description: CRM NetWorkle domain — entities, notes, graph, suggests, activity tasks, and files. Load when the user works with NetWorkle CRM, people, organizations, notes, or CRM daily context.
depends_on: crm-entities crm-notes crm-graph crm-ops work-items document-workspace team-directory
---

# Networkle (CRM)

## Goal

Operate NetWorkle CRM from Lara. Prefer this skill when the entry focus is CRM; available from any Lara entry.

## Procedure

1. Load `crm-entities` for entity CRUD, merge, types, summaries, activity-task create/list, embed blocks.
2. Load `crm-notes` for note create/analyze/apply/discard and note listing.
3. Load `crm-graph` for relationship list/delete/types and neighborhood/path.
4. Load `crm-ops` for suggests and knowledge-import status.
5. Load `work-items` after creating a CRM activity task — work fields live on WorkItem.
6. Load `document-workspace` for files/attachments; `team-directory` for assignees/members.
7. Use session variables (`user_*`, `company_*`, `active_namespace`, `crm_lara_summary_json`) — do not re-ask for JWT identity.
8. Answer in the user's interface language (`interface_language_code` / `interface_language_name`).

## Capability boundary

AmoCRM admin, grants/access-requests, entity-type/template authoring, graph 3d/mindmap chrome — no Lara operational tools; explain the CRM UI path.

## Naming

- CRM node id is `entity_id` (notes: same id as `note_id`).
- Activity work id is `work_item_id` (kind `crm_activity`) — not a duplicate of `entity_id`.
- Suggest id is `suggest_id`. Relationship id is `relationship_id`.

## Reference

Read `networkle-lara-crm-methodology.md` for the intent→tool matrix and note AI lifecycle.
