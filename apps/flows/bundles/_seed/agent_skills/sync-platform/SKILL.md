---
name: sync-platform
description: Sync collaboration service — channels, threads, messages, files, Git context, and calls. Load for Sync chat work and engineering collaboration.
allowed-tools: sync_list_messages sync_send_message
---

# Sync

## Goal

Help users work in Sync with real channel context and the existing message tools.

## Procedure

1. Use `channel_id`, `thread_id`, `message_id`, `call_id` and `git_ref_id` from session/UI context; never derive an id from a title.
2. Read recent channel context with `sync_list_messages` before summarizing a conversation when the supplied context is insufficient.
3. Call `sync_send_message` only when the user explicitly asks to send. Preserve the requested meaning, channel and optional thread; do not silently broadcast a draft.
4. For attached files, load root `platform-workspace`, then `document-workspace`.
5. For follow-ups and reminders, load `platform-workspace`, then `work-tracking`.

## Capability boundary

The tools cover listing and sending messages. Git operations, channel administration, calls, recordings, participants and reactions have no Lara operational tool. For those tasks, explain the Sync UI workflow and do not claim execution.

## Rules

- Use canonical `channel_id`, `thread_id`, `message_id`, `call_id` and `git_ref_id`.
- Summaries must distinguish tool-returned messages from assumptions.
- Do not send credentials or secret values into a channel.
