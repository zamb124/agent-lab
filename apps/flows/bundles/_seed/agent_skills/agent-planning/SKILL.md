---
name: agent-planning
description: Maintain a visible execution checklist for multi-step work. Use when a task needs several tool calls, research steps, or clear progress for the user. Load before long runs.
allowed-tools: agent_plan_write agent_plan_get
---

# Agent planning

## Goal

Keep a short, accurate checklist of what you are doing so the user sees progress and you stay oriented across tool calls.

## Procedure

1. At the start of a multi-step task — `agent_plan_write` with the full planned steps (one `in_progress`, rest `pending`).
2. After each meaningful step finishes — `agent_plan_write` again with the **entire** updated list (full replace; never a delta).
3. When unsure what is current — `agent_plan_get` (fails if you never wrote a plan).
4. If you need the user — set the blocking step to `need_help`, then `ask_user` (or HITL). Do not invent answers.
5. When done — mark all steps `completed` with a final `agent_plan_write`.

## Rules

- Always send the **full** `steps` array on every write.
- At most one step with status `in_progress`.
- Step `id` values stay stable (`"1"`, `"2"`, …); change only `status` / `title` when needed.
- Titles are one short phrase each; no essays in the plan.
- Do not use WorkItem tools for micro-steps of the plan. WorkItems are durable human/queue work; AgentPlan is the run checklist.
- Do not put the checklist into `reason.plan` instead of these tools — `reason` is prose analysis; AgentPlan is the structured checklist.

## Notes

- Read `references/agent-planning-methodology.md` for examples and anti-patterns.
- Skip planning for a single trivial tool call or a one-line answer.
