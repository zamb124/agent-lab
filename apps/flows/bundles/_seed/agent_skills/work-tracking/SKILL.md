---
name: work-tracking
description: Create and complete WorkItems, list mine/company work, and manage one-time or recurring schedules. Use for work, follow-ups, reminders, and work lists.
allowed-tools: work_item_create work_item_list work_item_list_mine work_item_complete schedule_cron_task schedule_interval_task schedule_one_time_task list_scheduled_tasks cancel_scheduled_task
depends_on: team-directory
---

# Work tracking

## Goal

Track WorkItems and lightweight schedules. Prefer this shared leaf from any service; load `work-items` / `work-queues` / `work-boards` under `worktracker-platform` for full lifecycle.

## Intent → tool

| Intent | Tool |
|---|---|
| What is on me? | `work_item_list_mine` |
| Filtered company / board / queue list | `work_item_list` (never for «mine») |
| Create work | `work_item_create` (board via create_manual_task semantics) |
| Complete done/failed | `work_item_complete` |
| Assign to a named person | `team_resolve_user` → then create/assign with `user_id` |
| One-time / cron / interval reminder | `schedule_*` / `list_scheduled_tasks` / `cancel_scheduled_task` |

## Procedure

1. Open work for the current actor — `work_item_list_mine` (default excludes terminal).
2. Create — `work_item_create` with a clear title; for a person resolve `user_id` via `team_resolve_user` first; for a queue use `assignee_queue_slug`.
3. Complete — `work_item_complete` with exact `work_item_id` from list/create (optional `terminal_state=failed`).
4. Schedules — `schedule_one_time_task` / `schedule_cron_task` / `schedule_interval_task`; inspect with `list_scheduled_tasks`; cancel with `cancel_scheduled_task`.

## Rules

- Never invent `work_item_id` / `user_id` / `work_queue_id`.
- Do not use `work_item_list` for «my tasks».
- Cancel is not complete — load `work-items` for `work_item_cancel`.
- Clarify timezone before wall-clock schedules when not explicit.
