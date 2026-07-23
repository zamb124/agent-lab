---
name: work-items
description: Full WorkItem lifecycle — get, update, assign, move, claim, cancel, comments, mine summary. Load after work-tracking for day-to-day task operations.
allowed-tools: work_item_get work_item_update work_item_assign work_item_move work_item_claim work_item_cancel work_item_add_comment work_item_list_comments work_item_mine_summary
depends_on: team-directory work-tracking
---

# Work items

## Goal

Operate on existing WorkItems like the Worktracker detail page (except HITL customer chat).

## Intent → tool

| Intent | Tool |
|---|---|
| Full detail | `work_item_get` |
| Inbox counters / my queue ids | `work_item_mine_summary` |
| Edit fields | `work_item_update` |
| Reassign | `team_resolve_user` / queue slug → `work_item_assign` |
| Kanban move | `work_board_get` → `work_item_move` |
| Claim queue item | `work_item_claim` (must be queue member) |
| Cancel | `work_item_cancel` |
| Activity note | `work_item_add_comment` / `work_item_list_comments` |

## Procedure

1. After assignment wake-up: prefer `work_item_get` when `work_item_id` is known; else `work_item_list_mine` then get.
2. Work → optional `work_item_update` / comments → `work_item_complete` or `work_item_cancel`.
3. Reassign people only with ids from `team_resolve_user` / `team_list_members` (ask_user if ambiguous).

## Rules

- Comments are internal activity — not HITL conversation with an external user.
- Do not invent ids. Terminal cancel ≠ complete(failed).
