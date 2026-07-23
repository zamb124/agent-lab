---
name: crm-notes
description: List CRM notes and run the note AI lifecycle — create (confirm-first), analyze, apply or discard analysis draft.
allowed-tools: crm_search_entities crm_get_entity crm_list_entity_types crm_list_notes crm_create_note crm_analyze_note_text crm_apply_analysis_draft crm_discard_analysis_draft crm_create_note_and_analyze
---

# CRM notes

## Goal

Find CRM entities and capture structured notes with AI analysis draft lifecycle (Lara NetWorkle).

## Procedure

1. Discover types — `crm_list_entity_types` if unsure.
2. Find entities — `crm_search_entities`, then `crm_get_entity`.
3. List notes — `crm_list_notes` with `date_from` / optional `date_to` (YYYY-MM-DD).
4. New note — `crm_create_note` confirm-first: `mode=propose` → user confirm → `mode=apply` with `pending_action_id`.
5. After create, ask via chat whether to run AI analysis; do not analyze without confirmation.
6. Analyze — `crm_analyze_note_text(note_id)` writes draft only.
7. Close the loop — `crm_apply_analysis_draft` **or** `crm_discard_analysis_draft`.
8. Create + analyze in one step — `crm_create_note_and_analyze` only when the user explicitly asks both.

## Rules

- Never invent `entity_id` / `note_id`.
- Analyze ≠ apply. Draft counters in session require apply or discard.
- Do not call `crm_analyze_note_text` right after create unless the user agreed.
- Confirm-first: `assistant:action_previewed` → user confirm → apply.
- After a successful tool, briefly summarize; do not dump full JSON.
