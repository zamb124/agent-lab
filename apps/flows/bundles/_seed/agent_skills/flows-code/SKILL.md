---
name: flows-code
description: Flows code and node-config subdomain — code nodes, llm_node config, and generic node edits. Load when editing node source or node settings in the Flows editor.
depends_on: code-node llm-node-config flows-node-edit flows-editor
---

# Flows code / node config

## Goal

Specialize on code and per-node configuration while staying connected to the Flows editor patch tools.

## Procedure

1. Code node work — load `code-node`.
2. llm_node prompt/tools/skills — load `llm-node-config`.
3. Other node types — load `flows-node-edit`.
4. Flow-level or multi-object patches — load `flows-editor`.

## Cross-domain

NetWorkle / docs / workspace skills remain available from the Tier-1 Lara index.
