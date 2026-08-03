---
name: wiki-platform
description: Wiki knowledge base — page tree, markdown content, access, public links, search, revisions, comments. Load from the Wiki SPA or for knowledge-base tasks.
depends_on: wiki-pages wiki-access wiki-discovery team-directory knowledge-rag document-workspace
---

# Wiki service

## Goal

Choose the correct Wiki workflow and keep identifiers distinct: `wiki_page_id` ≠ `file_id` (Documents) ≠ `document_id` (RAG).

## Procedure

1. Use `wiki_page_id` and `active_namespace` from UI context; never invent ids.
2. Load child `wiki-pages` for tree, markdown read/write, properties, move, trash, import, revisions, comments.
3. Load child `wiki-access` for members and public links (`depends_on` team-directory for `user_id`).
4. Load child `wiki-discovery` for search and backlinks.
5. Attach cover/files — `document-workspace` / `create_file`, then `wiki_update_properties(cover_url=...)` or markdown embeds.
6. Broader company knowledge — `knowledge-rag` (`rag_*`), not a substitute for `wiki_search` on pages.
7. Read reference `wiki-employee-methodology.md` for intent→tool chains.

## Capability boundary

Tools cover authenticated Wiki REST: tree, markdown content, properties, move, trash, import, revisions, comments, ACL, public link rotate, search, backlinks, namespace list.

Outline/TOC chrome, sticky UI prefs, emoji picker UI, anonymous public SPA browsing, and creating company namespaces have no Lara operational tool — explain the Wiki UI / platform namespace path without claiming a mutation.
