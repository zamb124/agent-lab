---
name: crm-notes
description: Search CRM entities and create or analyze CRM notes. Use when the user talks about people, organizations, relationships, or CRM note capture.
allowed-tools: crm_search_entities crm_get_entity crm_list_entity_types crm_create_note crm_analyze_note_text crm_create_note_and_analyze
activation: explicit
---

# CRM notes

## Goal

Find CRM entities and capture structured notes with optional AI analysis.

## Procedure

1. Discover types — `crm_list_entity_types` if the user is unsure.
2. Find entities — `crm_search_entities`, then `crm_get_entity` for details.
3. New note only — `crm_create_note`.
4. Analyze free text — `crm_analyze_note_text`.
5. Create + analyze in one step — `crm_create_note_and_analyze`.

## Notes

- Never invent `entity_id`; use search results.
- Confirm namespace/context when tools require it.
