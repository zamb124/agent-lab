---
name: wiki-pages
description: Create, read, edit, move, trash, import markdown, revisions, and comments for Wiki pages. Use when the user works with knowledge-base pages or tree.
allowed-tools: wiki_list_tree wiki_list_namespaces wiki_get_page wiki_get_markdown wiki_create_page wiki_update_markdown wiki_update_properties wiki_move_page wiki_move_page_namespace wiki_delete_page wiki_list_deleted wiki_restore_page wiki_import_markdown wiki_parse_markdown wiki_list_revisions wiki_get_revision wiki_restore_revision wiki_list_comments wiki_create_comment wiki_resolve_comment wiki_delete_comment
---

# Wiki pages

## Goal

Operate the Wiki page tree and content in the active namespace without inventing ids.

## Procedure

1. Orient — `wiki_list_namespaces` / `wiki_list_tree` for parents and structure.
2. Read — `wiki_get_page` for metadata; **`wiki_get_markdown` for body** (never invent ProseMirror JSON).
3. Create — `wiki_create_page(title, markdown, parent_page_id?)`.
4. Edit body — `wiki_update_markdown(wiki_page_id, markdown, title?)`.
5. Properties — `wiki_update_properties` (icon, cover_url, is_published, is_full_width, is_template). Cover/files: load `document-workspace` / `create_file`, then set `cover_url` or embed markdown `![](...)` / `platform-file:`.
6. Move — `wiki_move_page` / `wiki_move_page_namespace`.
7. Trash — `wiki_delete_page` → `wiki_list_deleted` → `wiki_restore_page`.
8. Import file — `wiki_import_markdown` (omit `wiki_page_id` to create; pass it to replace). Preview gaps with `wiki_parse_markdown`.
9. History — `wiki_list_revisions` → `wiki_get_revision` → `wiki_restore_revision`.
10. Comments — `wiki_list_comments` / `wiki_create_comment` / `wiki_resolve_comment` / `wiki_delete_comment`.

## Rules

- Never invent `wiki_page_id`. Take it from tools, UI context, or search.
- Namespace comes from session (`X-Platform-Namespace`); tools fail closed if missing.
- Do not PATCH `visibility` — restricted/company is member-driven (`wiki-access`).
- Search/backlinks — skill `wiki-discovery`. ACL/public link — `wiki-access`.
