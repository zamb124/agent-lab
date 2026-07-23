# Sync employee methodology

## Wake-up

When the flow runs because of `sync/message/created` (DM or @mention):

1. Prefer `channel_id` from run/UI context.
2. Else `sync_list_channels` → pick the chat → use its `channel_id`.
3. `sync_list_messages` (optional cursor) to read context.
4. Resolve peer with `team_resolve_user` / `sync_list_channel_members` when @mention is needed.
5. `sync_send_message` with explicit text; in groups pass `mentioned_user_ids` so the human is woken symmetrically.
6. Optional `sync_mark_channel_read` after handling.

## Scenario matrix

| Intent | Chain |
|---|---|
| What chats do I have? | `sync_list_channels` |
| Read channel | `sync_list_messages` (+ before/after) |
| Reply in DM | `sync_send_message` |
| Reply in group with wake | `team_resolve_user` → `sync_send_message(mentioned_user_ids=[…])` |
| Reply in thread | `sync_list_thread_messages` → `sync_send_message(thread_id=…)` |
| Open / create thread | `sync_create_thread` / `sync_list_threads` |
| Start DM | `team_resolve_user` → `sync_create_channel(type=direct, member_ids=[peer])` |
| Add member | `team_resolve_user` → `sync_add_channel_member` |
| Mark read | `sync_mark_channel_read` |
| React / edit / delete | `sync_react_message` / `sync_edit_message` / `sync_delete_message` |

## Boundaries

- Calls, Git, presence/typing — UI only.
- Group without @mention does not wake the employee (by design).
- Never invent `channel_id` / `message_id` / `user_id`.
