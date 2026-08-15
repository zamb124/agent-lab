---
name: wiki-access
description: Manage Wiki page members, restricted visibility, and public site links. Use when the user asks who can see a page or for a shareable public URL.
allowed-tools: wiki_get_access wiki_set_company_visible wiki_set_member wiki_remove_member wiki_rotate_public_link
depends_on: team-directory
---

# Wiki access

## Goal

Administer page ACL and public links correctly: `company_visible` is a direct per-page flag (does not cascade), while `viewer`/`editor` member relations do cascade to descendants.

## Procedure

1. Inspect — `wiki_get_access(wiki_page_id)` (company_visible, members, inherited_from_page_id, link flags; no raw URL).
2. Restrict — `wiki_set_company_visible(wiki_page_id, company_visible=false)` first (members are rejected while `company_visible=true`). Then resolve `user_id` via `team_resolve_user` / `team_list_members` and grant with `wiki_set_member(relation=viewer|editor)`.
3. Open to company — `wiki_set_company_visible(wiki_page_id, company_visible=true)`; this clears all explicit members automatically.
4. Public site — page must be `is_published` (`wiki_update_properties`). Then `wiki_rotate_public_link(enabled=true)` — **store/show `url` immediately**; it cannot be recovered later. Disable with `enabled=false`.

## Rules

- Never invent `user_id` or `wiki_page_id`.
- `company_visible` is a direct tuple per page, not inherited; a new child page snapshots its parent's current `company_visible` at creation time only.
- `viewer`/`editor` member relations do cascade to descendants; UI shows `inherited_from_page_id` for the nearest restricted ancestor.
- Public `/wiki/s/...` viewer is anonymous UI — Lara manages the link, not anonymous write APIs.
- Content edits — skill `wiki-pages`.
