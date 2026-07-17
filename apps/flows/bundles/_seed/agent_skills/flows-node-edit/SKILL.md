---
name: flows-node-edit
description: Patch a single Flows node with type-specific guidance (llm, nested flow, remote_flow, external_api, mcp, channel, hitl, resource). Use from node AI helper surfaces.
allowed-tools: flows_get_node flows_patch_node
---

# Flows node edit

## Goal

Make narrow, confirm-first patches to the currently selected node.

## Context

Standing IDs: `flow_id`, `target_branch_id`, `node_id`, `node_type`, `editor_dirty`.
Fetch the node body with `flows_get_node` before editing. For code nodes prefer skill `code-node`.

## Tools

1. `flows_get_node` — load the selected node from saved flow state.
2. `flows_patch_node` — `mode=propose` then `mode=apply` after explicit confirmation with the same `pending_action_id`.

Do not patch flow-level fields, other nodes, resources, edges, or triggers here.

## Specialization by `node_type` / assistant branch

- `llm_node`: prompt, model config, tools, `messages_filter`, mappings, `output_key`, `agent_skills`.
- nested `flow`: nested flow contract, I/O mappings, state propagation.
- `remote_flow`: A2A/external flow contract, payload mapping, errors.
- `external_api`: HTTP contract, auth/config, request/response mapping.
- `mcp`: server/tool selection, args, result mapping.
- `channel`: inbound/outbound channel settings and payload mapping.
- `hitl_node`: operator queue, interrupt payload, resume mapping.
- `resource`: resource binding and node-level overrides.
- unknown: keep patches minimal; explain gaps.

## Rules

1. If `editor_dirty=true`, ask to save before get/patch.
2. Briefly explain what you see after `flows_get_node` and how it relates to the branch.
3. Propose narrow edits only.
4. If data is missing, ask a short chat question (standing `ask_user` may be available on Lara).
5. Never invent ids or external API signatures.
6. Always propose before apply.

## Reference

Read `flows-node-edit-lara-methodology.md` for the full former Lara node helper specialization text.
