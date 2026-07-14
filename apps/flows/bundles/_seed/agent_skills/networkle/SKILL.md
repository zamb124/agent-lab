---
name: networkle
description: CRM NetWorkle domain — entities, notes, files, and UI blocks. Load when the user works with NetWorkle CRM, people, organizations, notes, or CRM daily context.
depends_on: crm-entities crm-notes document-workspace
---

# Networkle (CRM)

## Goal

Operate NetWorkle CRM from Lara. Prefer this skill when the entry focus is CRM, but it is available from any Lara entry.

## Procedure

1. Load child `crm-entities` for search/create/get/relationships/types/daily summary and embed blocks.
2. Load child `crm-notes` for note create/analyze lifecycle.
3. Load child `document-workspace` when files must be created or read for CRM work.
4. Use session variables (`user_*`, `company_*`, `active_namespace`, `crm_lara_summary_json`) as identity/context — do not re-ask for JWT identity.
5. Answer in the user's interface language (`interface_language_code` / `interface_language_name`).

## Cross-domain

If the user switches to Flows editor / docs / viz / work items, load the matching domain skill from the Tier-1 index (`flows-platform`, `docs-knowledge`, `platform-workspace`, …).

## Reference

Read `networkle-lara-crm-methodology.md` for the full former Lara CRM procedure text (confirm-first notes, tool nuances).
