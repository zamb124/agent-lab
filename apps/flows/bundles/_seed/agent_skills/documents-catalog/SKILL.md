---
name: documents-catalog
description: Browse, search, read, link, administer Documents catalogs (folders, members, ACL, public links) and catalog RAG index. Platform builtins for Flows llm_node and Lara.
allowed-tools: documents_list_catalog documents_find documents_read documents_get_link documents_create_catalog documents_update_catalog documents_list_catalog_members documents_add_catalog_member documents_get_access documents_patch_access documents_rotate_public_link documents_catalog_rag_status documents_catalog_rag_enable documents_catalog_rag_disable documents_catalog_rag_rebuild
---

# Documents catalog

## Goal

Navigate and administer the Documents library (catalogs + documents) without inventing ids.

## Procedure

1. Browse — `documents_list_catalog` without `catalog_id` for root catalogs; with `catalog_id` for children + documents (non-recursive).
2. Find — `documents_find(query, catalog_id?, mode=auto|semantic|lexical)`. Prefer `auto`.
3. Read — `documents_read(file_id, page_start, page_end)`.
4. SPA path — `documents_get_link(file_id, kind=editor|preview)`. Does **not** create a public internet share.
5. Folders — `documents_create_catalog` / `documents_update_catalog`.
6. Members — `documents_list_catalog_members` → resolve `user_id` via `team-directory` → `documents_add_catalog_member`.
7. ACL — `documents_get_access` / `documents_patch_access` (`resource_kind=catalog|document`).
8. Public share — enable link via patch, then `documents_rotate_public_link` for a fresh `/documents/p/…` URL.
9. Catalog RAG — `documents_catalog_rag_status` → `enable` / `rebuild` / `disable`; then semantic `documents_find`.

## Rules

- Never invent `catalog_id` or `file_id`.
- Never pass catalog/UI `file_id` to `read_agent_skill_reference` — that tool is only for skill methodology/assets from `load_agent_skill`; catalog documents use `documents_read`.
- File create/edit/trash — load `document-workspace`.
- Company knowledge outside catalog index — `knowledge-rag`.
