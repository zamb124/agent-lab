---
name: code-node
description: Edit Flows code nodes with isolated runner / capability-gateway contracts and inline code documentation. Use when helping with code_node source, mappings, or runner errors.
allowed-tools: flows_patch_node
---

# Code node

## Goal

Help with Flows `code` nodes: source, mappings, branch code resources, isolated runners, capabilities.

## Context (source of truth)

- `branch_code_payload_json` — selected code node, all branch code nodes, code resources, entry, edges, variable keys.
- `code_inline_documentation_md` — canonical inline SDK/docs for the node language (same as editor docs). If `code_inline_documentation_error` is set, say so and do not invent APIs.
- Also: `node_payload_json`, `flow_id`, `target_branch_id`, `node_id`, `selected_code_node_language`, `dataflow_node_json`, `lara_ui_context_json`.

## Runtime contract

User code never runs in-process inside `flows`. Path: runtime → `RemoteCodeRunner` → `code-runner-*` → `capability-gateway`. Do not suggest in-process `exec`/`eval`, `apps.*`/`core.*` imports, language-specific platform APIs, or mock fallbacks.

Prefer attribute-style state access in Python/JS examples (`state.session_id`). Capabilities come from `code_inline_documentation_md` / CapabilityManifest.

## Tool

`flows_patch_node` only: `mode=propose` then confirm then `mode=apply`. Do not patch other nodes/flow-level fields here.

## Rules

1. Explain the selected code node and branch relationships first.
2. Prefer narrow patches: async/await, explicit return, mappings, capabilities, join/dataflow issues.
3. Ask short clarifying questions in chat when needed.
4. Never invent signatures, local files, or platform imports.
5. On runner errors, use the structured error payload fields when available.

## Reference

Read `code-node-lara-methodology.md` for the full former Lara code helper contract (runners, state, capabilities).
