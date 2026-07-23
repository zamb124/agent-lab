---
name: sync-channels
description: List/create/update Sync channels, members, mark channel read, mute notifications.
allowed-tools: sync_list_channels sync_list_channel_members sync_mark_channel_read sync_create_channel sync_update_channel sync_add_channel_member sync_channel_notification_settings
depends_on: team-directory
---

# Sync channels

## Goal

Discover and administer Sync channels the current actor may access.

## Intent → tool

| Intent | Tool |
|---|---|
| My chats | `sync_list_channels` |
| Who is in the channel | `sync_list_channel_members` |
| Clear unread | `sync_mark_channel_read` |
| Start DM | `team_resolve_user` → `sync_create_channel(type=direct)` |
| Create topic | `sync_create_channel(type=topic, name, namespace)` |
| Rename / privacy | `sync_update_channel` |
| Invite member | `team_resolve_user` → `sync_add_channel_member` |
| Mute / unmute | `sync_channel_notification_settings` |

## Rules

- Peer `user_id` only from team tools.
- Company roster ≠ channel members.
- Calls/Git remain UI-only (parent skill boundary).
