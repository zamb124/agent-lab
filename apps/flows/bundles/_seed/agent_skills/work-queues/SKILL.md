---
name: work-queues
description: WorkQueue CRUD and queue membership. Load to manage operator/agent queues and claim access.
allowed-tools: work_queue_list work_queue_get_by_slug work_queue_create work_queue_update work_queue_list_members work_queue_add_member work_queue_remove_member
depends_on: team-directory
---

# Work queues

## Goal

Manage WorkQueues and who may claim queue-assigned WorkItems.

## Intent → tool

| Intent | Tool |
|---|---|
| List queues | `work_queue_list` |
| Resolve slug | `work_queue_get_by_slug` |
| Create / update | `work_queue_create` / `work_queue_update` |
| Who is in the queue | `work_queue_list_members` |
| Add / remove member | `team_resolve_user` → `work_queue_add_member` / `work_queue_remove_member` |

## Rules

- Queue members ≠ company roster (`team_list_members`).
- Use opaque `work_queue_id` / `user_id` from tools only.
