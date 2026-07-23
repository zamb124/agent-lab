---
name: sync-messaging
description: List and send Sync messages, edit/delete/react, mark message read. Use for channel conversation work.
allowed-tools: sync_list_messages sync_send_message sync_edit_message sync_delete_message sync_react_message sync_mark_message_read
depends_on: team-directory
---

# Sync messaging

## Goal

Read and write Sync root-lane messages as the current actor.

## Intent → tool

| Intent | Tool |
|---|---|
| Read channel lane | `sync_list_messages` (cursor before/after) |
| Send text | `sync_send_message` (optional thread_id, parent_message_id, mentioned_user_ids) |
| Edit own text | `sync_edit_message` |
| Delete | `sync_delete_message` |
| React | `sync_react_message` |
| Mark one message read | `sync_mark_message_read` (not channel unread) |

## Procedure

1. After wake — list with `channel_id` from context.
2. Before @mention — `team_resolve_user` / `sync_list_channel_members`.
3. Send only when the user asked to send.
4. Thread history — load `sync-threads` and call `sync_list_thread_messages`, not this list.

## Rules

- Never invent ids.
- `sync_list_messages` is root lane only (`thread_id` null).
- Channel discovery is `sync_list_channels`.
