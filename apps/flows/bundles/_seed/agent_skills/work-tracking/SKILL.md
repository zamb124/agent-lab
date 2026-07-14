---
name: work-tracking
description: Create and complete WorkItems and manage one-time schedules. Use for tasks, follow-ups, reminders, and work lists.
allowed-tools: work_item_create work_item_list work_item_complete schedule_one_time_task list_scheduled_tasks cancel_scheduled_task
activation: explicit
---

# Work tracking

## Goal

Track work items and lightweight one-time schedules.

## Procedure

1. List open work — `work_item_list`.
2. Create a task — `work_item_create` with a clear title and assignment if known.
3. Complete — `work_item_complete` with `work_item_id` from list/create.
4. Reminders — `schedule_one_time_task`; inspect with `list_scheduled_tasks`; stop with `cancel_scheduled_task`.

## Notes

- Use canonical `work_item_id` / schedule ids from tool responses.
- Ask the user before cancelling schedules they did not request to cancel.
