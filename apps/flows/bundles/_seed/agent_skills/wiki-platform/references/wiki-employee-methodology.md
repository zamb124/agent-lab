# Wiki employee methodology

## Context first

Prefer IDs from Wiki UI / Lara context:

1. `wiki_page_id` — open page (never invent; never swap with `file_id` / `document_id`).
2. `active_namespace` — workspace slug from session (`X-Platform-Namespace`).
3. `parent_page_id` — from `wiki_list_tree` when nesting.

Tools fail closed without a valid namespace.

## Eval / code_node

In isolated code (`code_node` / CodeTool) prefer the SDK namespace, not tool ids:

```python
page = await wiki.create_page(title="Onboarding", markdown="# Hello")
body = await wiki.get_markdown(wiki_page_id=page["wiki_page_id"])
```

Lara / LLM still loads skills and calls `wiki_*` tools; tools are thin wrappers over the same `WikiClient`.

## Scenario matrix

| Intent | Chain |
|---|---|
| What workspaces exist? | `wiki_list_namespaces` |
| Show tree | `wiki_list_tree` |
| Read page | `wiki_get_page` + `wiki_get_markdown` |
| Create page | `wiki_create_page(title, markdown, parent_page_id?)` |
| Edit body | `wiki_update_markdown` |
| Rename / icon / publish / full width / cover | `wiki_update_properties` |
| Move in tree | `wiki_move_page` |
| Move to another workspace | `wiki_move_page_namespace` |
| Trash / restore | `wiki_delete_page` → `wiki_list_deleted` → `wiki_restore_page` |
| Import .md | `wiki_parse_markdown` (optional) → `wiki_import_markdown` |
| History / restore version | `wiki_list_revisions` → `wiki_get_revision` → `wiki_restore_revision` |
| Comments | `wiki_list_comments` / `wiki_create_comment` / `wiki_resolve_comment` |
| Who can access? | `wiki_get_access` |
| Restrict page | `wiki_set_company_visible(company_visible=false)` → `team_resolve_user` → `wiki_set_member(relation=viewer\|editor)` |
| Company-wide again | `wiki_set_company_visible(company_visible=true)` (clears members automatically) |
| Public URL | ensure `is_published` → `wiki_rotate_public_link(enabled=true)` — show `url` once |
| Find pages | `wiki_search(mode=auto)` |
| Who links here? | `wiki_list_backlinks` |
| Cover / attachment file | `create_file` / Documents tools → `cover_url` or markdown embed |

## Markdown-first

- Read/write body only via markdown tools (`wiki_get_markdown`, `wiki_update_markdown`, `wiki_import_markdown`).
- Do not construct ProseMirror `content` JSON in tool args.
- Import notices mean dialect gaps — report them; do not claim silent fidelity.

## Visibility model

- `company_visible: bool` is a direct per-page flag (OpenFGA `company` tuple), not derived and not cascading.
- Members (`viewer`/`editor`) are only accepted while `company_visible=false`; flipping it back to `true` clears them.
- `viewer`/`editor` member relations do cascade down the tree via `parent`; `inherited_from_page_id` reports the nearest restricted ancestor for UI.

## Public link

- DB stores only token hash; raw URL appears once after enable/rotate.
- Public site requires `link_enabled` **and** `is_published`.
- Anonymous `/wiki/s/...` is viewer-only; Lara does not call `/public/*` write APIs.
