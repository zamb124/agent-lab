---
name: worktracker-platform
description: Worktracker service — WorkItems, queues, boards, assignment, completion, comments, and team lookup. Load from Worktracker or for structured work management.
depends_on: work-tracking work-items work-queues work-boards team-directory
---

# Worktracker service

## Goal

Help users and flow employees manage work with canonical WorkItem terminology and operational tools.

## Procedure

1. Use real `work_item_id`, `work_queue_id`, `board_id`, `board_column_id`, `user_id` from UI context or tool responses.
2. Load `work-tracking` for list_mine / create / complete / schedules.
3. Load `work-items` for get / update / assign / move / claim / cancel / comments.
4. Load `work-queues` / `work-boards` for queue and board admin.
5. Load `team-directory` before assigning to a named person.
6. Read `worktracker-employee-methodology.md` for employee inbox and scenario matrix.

## Capability boundary

HITL customer conversation (`/flows/.../hitl/...`) is operator-only — not available as Worktracker employee tools. Activity comments are internal. WorkItem delete is not exposed.

## Naming

The work entity is `WorkItem` with `work_item_id`. `task_id` is not an alias for it.
