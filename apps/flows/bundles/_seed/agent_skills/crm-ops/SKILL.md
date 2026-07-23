---
name: crm-ops
description: CRM operational inbox — suggests list/resolve/dismiss and knowledge-import task status.
allowed-tools: crm_list_suggests crm_resolve_suggest crm_dismiss_suggest crm_knowledge_import_status
---

# CRM ops

## Goal

Act on NetWorkle suggests and inspect knowledge-import job status (session counters become actionable).

## Procedure

1. Pending suggests — `crm_list_suggests` (namespace from session).
2. Accept — `crm_resolve_suggest(suggest_id)`.
3. Reject — `crm_dismiss_suggest(suggest_id)`.
4. Import jobs — `crm_knowledge_import_status` when counters show awaiting review / in progress.

## Rules

- Never invent `suggest_id` / `task_id`.
- Starting a new knowledge import from arbitrary files/admin UI remains out of scope for Lara unless the user provides an existing safe start path; prefer status + CRM UI for upload.
- AmoCRM sync admin is out of scope.
