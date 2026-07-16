---
name: work-tracking
description: Create and complete WorkItems and manage one-time or recurring schedules. Use for work, follow-ups, reminders, recurring checks, and work lists.
allowed-tools: work_item_create work_item_list work_item_complete schedule_cron_task schedule_interval_task schedule_one_time_task list_scheduled_tasks cancel_scheduled_task
---

# Work tracking

## Goal

Track work items and lightweight one-time schedules.

## Procedure

1. List open work — `work_item_list`.
2. Create a task — `work_item_create` with a clear title and assignment if known.
3. Complete — `work_item_complete` with `work_item_id` from list/create.
4. One-time reminder — `schedule_one_time_task` with an explicit ISO 8601 `run_at`.
5. Calendar recurrence — `schedule_cron_task` when the user gives a wall-clock pattern such as weekdays at 09:00.
6. Fixed cadence — `schedule_interval_task` when the user gives elapsed minutes between runs.
7. Inspect schedules with `list_scheduled_tasks`; cancel with `cancel_scheduled_task`.

## Notes

- Use canonical `work_item_id` / schedule ids from tool responses.
- Ask the user before cancelling schedules they did not request to cancel.
- Clarify timezone before creating a wall-clock schedule when it is not explicit in context.
- For `content_type=tool_call`, use only a tool already available to the flow and provide its arguments explicitly.
