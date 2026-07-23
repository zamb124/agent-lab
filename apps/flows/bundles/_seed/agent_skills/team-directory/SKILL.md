---
name: team-directory
description: Company team roster — list members and resolve people by name/email for assignment. Shared across Worktracker, Sync, and other skills.
allowed-tools: team_list_members team_resolve_user
---

# Team directory

## Goal

Resolve opaque `user_id` values for people and flow employees in the active company before assign / queue membership / mentions.

## Intent → tool

| Intent | Tool |
|---|---|
| Show roster | `team_list_members` |
| «Assign to Ivan» | `team_resolve_user` → if 1 match use `user_id`; if 0 or N — `ask_user` |

## Rules

- Search is **company members only** (not global platform search).
- Never invent `user_id` from a display name.
- Flow employees appear with `is_flow_employee=true` and `flow_id`.
- Queue membership is a different tool (`work_queue_*_members`).
