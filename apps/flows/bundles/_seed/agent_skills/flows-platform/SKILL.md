---
name: flows-platform
description: Flows Builder domain — graph editing, branches, nodes, confirm-first patches. Load when the user builds or edits flows on the platform.
depends_on: flows-editor flows-code
---

# Flows platform

## Goal

Help users build and edit Flows: graphs, branches, nodes, mappings, confirm-first Lara patches.

## How Flows work (brief)

Flow = `FlowConfig` with `entry`, `nodes`, `edges`, `variables`, `resources`, `triggers`, `speech`. Branch is a graph variant inside `flow_id` (UI `base` = API `default`). Execution walks waves of nodes; joins use `incoming_policy` any/all. State is `ExecutionState`. Node types include `llm_node`, `code`, `flow`, `remote_flow`, `external_api`, `mcp`, `channel`, `hitl_node`, `resource`.

## Procedure

1. Load `flows-editor` for read/patch/embed tools and confirm-first lifecycle.
2. Load `flows-code` (then its children) for code / llm_node / typed node helpers.
3. Use editor variables (`lara_ui_context_json`, payloads) as source of truth.
4. Answer in the user's interface language.

## Cross-domain

If the user asks about NetWorkle CRM, docs, files, viz, or work items — load the matching Tier-1 domain skill (`networkle`, `docs-knowledge`, `platform-workspace`, …).

## Reference

Read `flows-platform-lara-methodology.md` for the full former Lara Flows Builder procedure.
