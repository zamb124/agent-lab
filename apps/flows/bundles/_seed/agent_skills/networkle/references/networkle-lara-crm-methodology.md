# Networkle (CRM) employee methodology

## Context first

Prefer IDs from CRM UI / Lara session:

1. `namespace` — `active_namespace` (do not invent `default`).
2. `entity_id` / `note_id` — from search/list/get or UI; never invent.
3. `work_item_id` — from `crm_create_activity_task` / `crm_list_activity_tasks` response; work mutations go through `work-items`.
4. Session counters (`crm_lara_summary_json`, draft/import flags) — hints only; act via tools.

## Scenario matrix

| Intent | Chain |
|---|---|
| Find person/org/note | `crm_search_entities` → `crm_get_entity` |
| Create entity | `crm_list_entity_types` (if unsure) → `crm_create_entity` |
| Fix / rename entity | `crm_get_entity` → `crm_update_entity` |
| Remove entity | `crm_delete_entity` (confirm with user) |
| Merge duplicates | `crm_merge_entities(survivor, source)` |
| Create note (confirm-first) | `crm_create_note(mode=propose)` → user confirm → `mode=apply` |
| Analyze note | ask user → `crm_analyze_note_text` |
| Apply AI draft | `crm_apply_analysis_draft(note_id)` |
| Discard AI draft | `crm_discard_analysis_draft(note_id)` |
| Notes for a day / range | `crm_list_notes(date_from, date_to?)` |
| Create + analyze immediately | `crm_create_note_and_analyze` only if user asked both |
| Link two entities | `crm_create_relationship` |
| List / delete links | load `crm-graph` → `crm_list_relationships` / `crm_delete_relationship` |
| Neighborhood / path | `crm_entity_related` / `crm_shortest_path` |
| Relationship type catalog | `crm_list_relationship_types` |
| Day digest | `crm_daily_summary` |
| Period digest | `crm_period_summary` |
| Pending suggests | load `crm-ops` → `crm_list_suggests` → resolve/dismiss |
| Knowledge import status | `crm_knowledge_import_status` |
| CRM activity task | `crm_create_activity_task` → then `work_item_*` via `work-items` |
| Assignees / members | load `team-directory` → `team_resolve_user` |
| Attachments / files | load `document-workspace` |

## Note AI lifecycle

1. `crm_create_note` (propose → apply) creates the note.
2. Ask whether to run analysis; never call `crm_analyze_note_text` without consent.
3. Analyze writes `ai_analysis_draft` — **not** graph mutations.
4. User reviews → `crm_apply_analysis_draft` **or** `crm_discard_analysis_draft`.
5. Analyze ≠ apply. Session counter `crm_notes_analysis_draft_not_applied` means apply/discard is still needed.

## Tasks: CRM node vs WorkItem

| Concept | Id | Tools |
|---|---|---|
| Graph node `entity_type=task` | `entity_id` | created via `crm_create_activity_task` |
| Work semantics (state/board/assignee) | `work_item_id` | `work_item_get` / `update` / `complete` / `move` / … |

Do not invent a second CRM kanban tool pack. After create, load `work-items` for work mutations.

## Boundaries (no operational tools)

- AmoCRM / namespace integration admin (OAuth, sync jobs).
- Grants / access-requests deep share flows.
- Entity-type / template / namespace authoring admin.
- Graph 3d / mindmap chrome, voice dictation UI.
- Bulk export / aggregate admin.

Explain the CRM UI path; do not claim execution.

## Anti-patterns

- Inventing `entity_id` / `note_id` / `suggest_id` / `relationship_id` / `work_item_id`.
- Treating analyze success as apply.
- Using CRM tools for WorkItem board/state fields.
- Calling tools that are not unlocked after `load_agent_skill`.
