---
name: llm-node-config
description: Configure llm_node prompt, tools, agent_skills, messages_filter, mappings, and output_key via confirm-first node patches.
allowed-tools: flows_get_node flows_patch_node
---

# LLM node config

## Goal

Edit `llm_node` configuration safely with propose/apply patches.

## Focus fields

prompt, LLM provider/model, standing `tools`, `agent_skills`, `messages_filter`, `input_mapping` / `output_mapping`, `output_key`.

## Procedure

1. Call `flows_get_node(flow_id, branch_id=target_branch_id, node_id)` for the current node body.
2. `flows_patch_node` `mode=propose` with a minimal patch.
3. After explicit user confirmation — `mode=apply` with `pending_action_id`.
4. Magic Agent Skill tools (`load_agent_skill`, `read_agent_skill_reference`) must not appear in standing tools chips; attach skills via `agent_skills` list.

## Rules

- Never invent `flow_id` / `node_id`.
- If `editor_dirty=true`, ask to save before get/patch.
- Prefer narrow diffs; explain impact on tool-calling and context.
