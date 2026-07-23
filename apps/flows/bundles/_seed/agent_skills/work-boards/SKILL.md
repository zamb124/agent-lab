---
name: work-boards
description: WorkItem boards and columns — list, get, create, update. Load before kanban moves or board admin.
allowed-tools: work_board_list work_board_get work_board_create work_board_update
---

# Work boards

## Goal

Inspect and configure kanban boards/columns used by `work_item_move`.

## Procedure

1. Discover — `work_board_list` (ensures generic board when empty).
2. Columns — `work_board_get` for `board_column_id` / `item_state`.
3. Admin — `work_board_create` / `work_board_update` (full column replace on update).
4. Move cards — load `work-items` and call `work_item_move`.

## Rules

- Never invent `board_id` / `board_column_id`.
- Terminal states on cards use complete/cancel, not move-to-done unless the column maps that state intentionally.
