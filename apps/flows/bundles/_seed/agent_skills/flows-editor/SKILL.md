---
name: flows-editor
description: Read and patch Flows editor context — flow/node propose-apply patches and chat embed blocks. Use when editing a flow graph or applying Lara confirm-first patches.
allowed-tools: flows_read_context flows_patch_node flows_patch_flow push_embed_blocks
---

# Flows editor

## Goal

Read live editor context and apply confirm-first patches to nodes or the flow.

## Context variables

Use when present: `screen`, `selection_source`, `flow_id`, `target_branch_id`, `assistant_branch_id`, `node_id`, `node_type`, `node_payload_json`, `flow_payload_json`, `lara_ui_context_json`.

## Procedure

1. Call `flows_read_context` when editor context is incomplete.
2. Node changes — `flows_patch_node`: `mode=propose` then after explicit user confirm `mode=apply` with the same `pending_action_id`.
3. Flow-level changes (e.g. rename) — `flows_patch_flow` with the same confirm-first lifecycle.
4. Structured UI — `push_embed_blocks` when helpful.

## Rules

- Never invent `flow_id` / `node_id`.
- After propose, always tell the user confirmation is required before apply.
- Rely on `assistant:action_previewed` / `applied` / `rejected` / `failed` for mutation UX.
