---
name: sync-threads
description: List/get/create Sync threads and list messages inside a thread.
allowed-tools: sync_list_threads sync_get_thread sync_create_thread sync_list_thread_messages
---

# Sync threads

## Goal

Work with Sync threads separately from the root message lane.

## Intent → tool

| Intent | Tool |
|---|---|
| List threads in channel | `sync_list_threads` |
| Thread metadata | `sync_get_thread` |
| Start thread from message | `sync_create_thread(root_message_id=…)` |
| Read thread history | `sync_list_thread_messages` |
| Reply in thread | load `sync-messaging` → `sync_send_message(thread_id=…)` |

## Procedure

1. Discover — `sync_list_threads`.
2. Read — `sync_list_thread_messages` (never `sync_list_messages` for threads).
3. Reply — `sync_send_message` with the same `thread_id`.

## Rules

- `thread_id` only from tools/context.
- Root lane and thread lane are different APIs.
