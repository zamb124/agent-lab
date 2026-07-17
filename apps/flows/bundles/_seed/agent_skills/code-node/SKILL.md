---
name: code-node
description: Edit Flows code nodes with isolated runner / capability-gateway contracts. Use when helping with code_node source, mappings, or runner errors.
allowed-tools: flows_get_node flows_list_nodes flows_patch_node
---

# Code node

## Goal

Help with Flows `code` nodes: source, mappings, branch code siblings, isolated runners, capabilities.

## Context

Standing IDs: `flow_id`, `target_branch_id`, `node_id`, `node_type`, `editor_dirty`.
Fetch bodies with tools:
- `flows_get_node` — selected code node (`code`, `language`, schemas, mappings).
- `flows_list_nodes` — sibling index when relationships matter (no code bodies).

## Runtime contract

User code never runs in-process inside `flows`. Path: runtime → `RemoteCodeRunner` → `code-runner-*` → `capability-gateway`. Do not suggest in-process `exec`/`eval`, `apps.*`/`core.*` imports, language-specific platform APIs, or mock fallbacks.

Prefer attribute-style state access in Python/JS examples (`state.session_id`).

## Tool

`flows_patch_node`: `mode=propose` then confirm then `mode=apply`. Do not patch other nodes/flow-level fields here.

## Rules

1. If `editor_dirty=true`, ask to save before get/patch.
2. Explain the selected code node after `flows_get_node` first.
3. Prefer narrow patches: async/await, explicit return, mappings, capabilities, join/dataflow issues.
4. Ask short clarifying questions in chat when needed.
5. Never invent signatures, local files, or platform imports.
6. On runner errors, use the structured error payload fields when available.

## Reference

Read `code-node-lara-methodology.md` for the full former Lara code helper contract (runners, state, capabilities).
