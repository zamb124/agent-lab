---
name: crm-entities
description: Search, create, and relate CRM NetWorkle entities and daily summaries. Use for people, organizations, relationships, entity types, and daily CRM digest.
allowed-tools: crm_search_entities crm_create_entity crm_get_entity crm_create_relationship crm_list_entity_types crm_daily_summary push_embed_blocks
---

# CRM entities

## Goal

Work with NetWorkle CRM graph entities (search, create, get, relationships, types, daily summary) and optional UI embed blocks.

## Procedure

1. Discover types — `crm_list_entity_types` when the user is unsure about `entity_type` / `entity_subtype`.
2. Search — `crm_search_entities` with the user's query string; set type filters only if the user asked; do not invent `namespace` (session supplies it); default `limit` 100.
3. Details — `crm_get_entity` with a real `entity_id` from search/results.
4. Create — `crm_create_entity` only with fields the user provided; never invent ids.
5. Relationships — `crm_create_relationship` with real source/target entity ids.
6. Daily digest — `crm_daily_summary` when the user asks for a day overview.
7. Structured UI — `push_embed_blocks` with `blocks_json` (`card`, `table`, `actions`, `file_card`, `text`) when a visual summary helps.

## Rules

- Never invent `entity_id`.
- After a successful tool call, briefly summarize for the user; do not dump raw JSON.
- Confirm-first mutations follow `propose` → user confirm → `apply` when the tool supports that lifecycle.
