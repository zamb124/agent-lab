---
name: flows-editor
description: Point-fetch Flows graph by ids and apply confirm-first node/flow patches plus chat embed blocks. Use when editing a flow graph from Lara.
allowed-tools: flows_get_node flows_list_nodes flows_read_context flows_patch_node flows_patch_flow ui_render
---

# Flows editor

## Goal

Fetch only the flow/node slices you need, then apply confirm-first patches.

## Context variables (IDs only)

Standing metadata may include: `screen`, `selection_source`, `flow_id`, `target_branch_id`, `api_branch_id`, `assistant_branch_id`, `node_id`, `node_type`, `branch_node_count`, `branch_edge_count`, `editor_dirty`.

There is **no** standing `*_payload_json` / full FlowConfig dump. Bodies come from tools. Tools read **saved** flow state; if `editor_dirty=true`, ask the user to save before read/patch.

## Procedure

1. Prefer `flows_get_node(flow_id, branch_id, node_id)` for a single node body (prompt/code/tools).
2. Prefer `flows_list_nodes(flow_id, branch_id)` for a branch index without prompt/code bodies.
3. Use `flows_read_context` for a light overview (flow summary + `nodes_index`, optional one `node`).
4. Node changes — `flows_patch_node`: `mode=propose` then after explicit user confirm `mode=apply` with the same `pending_action_id`.
5. Flow-level changes (e.g. rename) — `flows_patch_flow` with the same confirm-first lifecycle.
6. Structured UI — `ui_render` (slot_id `conversation`) when helpful.

## Rules

- Never invent `flow_id` / `node_id`.
- After propose, always tell the user confirmation is required before apply.
- Rely on `assistant:action_previewed` / `applied` / `rejected` / `failed` for mutation UX.
