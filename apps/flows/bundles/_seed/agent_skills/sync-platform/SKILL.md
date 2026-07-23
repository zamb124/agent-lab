---
name: sync-platform
description: Sync collaboration service — channels, threads, messages, and team lookup for chat work. Load for Sync or when answering as a flow employee in chat.
depends_on: sync-messaging sync-channels sync-threads team-directory
---

# Sync service

## Goal

Help users and flow employees work in Sync with canonical channel/message/thread ids and operational tools.

## Procedure

1. Use real `channel_id`, `thread_id`, `message_id`, `user_id` from UI context, inbox wake, or tool responses — never invent ids from titles.
2. Load `sync-messaging` for list/send/edit/delete/react/mark message read.
3. Load `sync-channels` for list/create/update channels, members, mark channel read, mute.
4. Load `sync-threads` for thread list/get/create and thread message history.
5. Load `team-directory` before @mention or assigning a peer to a DM.
6. Read `sync-employee-methodology.md` for inbox wake procedure.

## Capability boundary

Calls / LiveKit / recording / guest links, Git resources, presence and typing have no Lara operational tools — explain the Sync UI path, do not claim execution. Always-on group reply without @mention is intentionally unsupported.

## Naming

Message id is `message_id`. Channel id is `channel_id`. Do not call a Sync message a WorkItem `work_item_id`.
