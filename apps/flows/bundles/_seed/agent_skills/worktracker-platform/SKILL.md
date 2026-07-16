---
name: worktracker-platform
description: Worktracker service — WorkItems, queues, boards, columns, assignment, completion, and scheduled follow-ups. Load from Worktracker or for structured work management.
depends_on: work-tracking
---

# Worktracker service

## Goal

Help users manage work with canonical WorkItem terminology and the available work/scheduling tools.

## Procedure

1. Use real `work_item_id`, `work_queue_id`, `board_id` and `board_column_id` values from UI context or tool responses.
2. Load child `work-tracking` for WorkItem list/create/complete and one-time or recurring schedules.
3. Before creating work, confirm the title and assignment when either is ambiguous.
4. Before completing work, select the exact `work_item_id`; do not infer it from a repeated title.
5. Use schedules for future execution, not as a replacement for WorkItem state.

## Capability boundary

Board/column CRUD, card movement, queue membership, comments and assignment changes do not have Lara operational tools. Explain the Worktracker UI workflow and do not report a change as completed.

## Naming

The work entity is `WorkItem` with `work_item_id`. `task_id` is not an alias for it.
