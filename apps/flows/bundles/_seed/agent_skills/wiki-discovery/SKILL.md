---
name: wiki-discovery
description: Search Wiki pages (lexical/semantic) and list backlinks from platform entities. Use when finding pages by meaning or title, or who links to an entity.
allowed-tools: wiki_search wiki_list_backlinks
---

# Wiki discovery

## Goal

Find pages and reverse links without inventing ids.

## Procedure

1. Search — `wiki_search(query, mode=auto|semantic|lexical, root_page_id?, published_only?, limit?)`. Prefer `auto`.
2. Open hit — load `wiki-pages` → `wiki_get_markdown(wiki_page_id)`.
3. Backlinks — `wiki_list_backlinks(target_kind, target_id)` for `wiki_page` / `crm_entity` / `file` / `work_item` / `sync_message` / `url`.

## Rules

- Never invent `wiki_page_id` from titles alone — search first.
- Company-wide knowledge outside Wiki index — load `knowledge-rag`.
- Tree browse / CRUD — `wiki-pages`.
