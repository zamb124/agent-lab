---
name: crm-notes
description: Search CRM entities and create or analyze CRM notes. Use when the user talks about people, organizations, relationships, or CRM note capture.
allowed-tools: crm_search_entities crm_get_entity crm_list_entity_types crm_create_note crm_analyze_note_text crm_create_note_and_analyze
---

# CRM notes

## Goal

Find CRM entities and capture structured notes with optional AI analysis (Lara NetWorkle note lifecycle).

## Procedure

1. Discover types — `crm_list_entity_types` if the user is unsure.
2. Find entities — `crm_search_entities`, then `crm_get_entity` for details.
3. New note only — `crm_create_note` with confirm-first lifecycle:
   - first `mode=propose`;
   - after explicit user confirmation call `mode=apply` with `pending_action_id` from propose;
   - need `name`, `description`; optional `note_date` (YYYY-MM-DD);
   - after successful apply, briefly confirm creation;
   - then ask via chat whether to run AI analysis; do not analyze without confirmation.
4. Analyze free text — `crm_analyze_note_text` needs `text` and `note_id` of an existing note.
5. Create + analyze in one step — `crm_create_note_and_analyze` only when the user explicitly asks to create and analyze immediately.

## Rules

- Never invent `entity_id` / `note_id`.
- Do not call `crm_analyze_note_text` right after `crm_create_note` unless the user agreed to analysis.
- Confirm-first: `assistant:action_previewed` → user confirm → `assistant:action_applied` (or rejected/failed).
- After a successful tool, briefly summarize; do not dump full JSON.
