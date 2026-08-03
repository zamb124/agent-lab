---
name: wiki-access
description: Manage Wiki page members, restricted visibility, and public site links. Use when the user asks who can see a page or for a shareable public URL.
allowed-tools: wiki_get_access wiki_set_member wiki_remove_member wiki_rotate_public_link
depends_on: team-directory
---

# Wiki access

## Goal

Administer page ACL and public links correctly: visibility is derived from members, not a free-form field.

## Procedure

1. Inspect — `wiki_get_access(wiki_page_id)` (members, inherited_from_page_id, link flags; no raw URL).
2. Restrict — resolve `user_id` via `team_resolve_user` / `team_list_members`, then `wiki_set_member(permission=read|write|admin)`. First member → `restricted`.
3. Open to company — remove members with `wiki_remove_member` until none remain.
4. Public site — page must be `is_published` (`wiki_update_properties`). Then `wiki_rotate_public_link(enabled=true)` — **store/show `url` immediately**; it cannot be recovered later. Disable with `enabled=false`.

## Rules

- Never invent `user_id` or `wiki_page_id`.
- Inheritance: child pages inherit restriction from ancestors; UI shows `inherited_from_page_id`.
- Public `/wiki/s/...` viewer is anonymous UI — Lara manages the link, not anonymous write APIs.
- Content edits — skill `wiki-pages`.
