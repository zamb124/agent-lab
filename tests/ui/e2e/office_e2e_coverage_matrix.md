# Office UI: маршруты и покрытие E2E

Справочник для Playwright E2E (`tests/ui/e2e/test_office_*.py`). BFF/API-only операции (revisions, copy binding, events stream) не дублируются в Playwright.

## Маршруты `office-app` (`apps/office/ui/app/office-app.js`)

| routeKey | path | doc_slug / test file |
|----------|------|----------------------|
| `documents_list` | `/documents/` | `documents-complete-guide`, `workspace-and-catalogs`, `create-and-upload-documents`, `explorer-search-and-organize`, `document-actions-move-rename-delete`, `views-and-trash`, `catalog-rag-and-semantic-search` |
| `documents_recent` | `/documents/recent` | `views-and-trash` (`test_office_views_trash.py`) |
| `document_editor` | `/documents/edit/:bindingId` | `documents-complete-guide`, `edit-in-onlyoffice`, `view-other-file-types`, `mobile-documents-workflow` |
| `documents_public_preview` | `/documents/p/:token` | `public-link-preview` |
| `documents_catalogs` | legacy redirect | smoke в `documents-complete-guide` |
| `platform_services` | `/documents/services` | вне scope (platform launcher) |
| `document_editor_embed` | embed | backend only |

## Nav-rail (`office-explorer-nav-rail`)

| View | Покрытие |
|------|----------|
| All (catalog) | complete guide, explorer |
| Recent | views-and-trash |
| Starred | views-and-trash |
| Shared | disabled — не документируем |
| Deleted | views-and-trash |

## Модалки

| modalKind | doc_slug |
|-----------|----------|
| `office.namespace_create` | documents-complete-guide, workspace-and-catalogs |
| `office.catalog_create` | workspace-and-catalogs, create-and-upload-documents |
| `office.catalog_edit` | workspace-and-catalogs |
| `office.catalog_members` | catalog-access-and-members |
| `office.catalog_rag` | catalog-rag-and-semantic-search |
| `office.document_create_empty` | create-and-upload-documents, documents-complete-guide |
| `office.document_upload` | create-and-upload-documents, documents-complete-guide |
| `office.document_rename` | document-actions-move-rename-delete |
| `office.access` | share-catalog-and-document, catalog-access-and-members |

## Файлы тестов

| Файл | Сценарии |
|------|----------|
| `test_office_complete_guide.py` | documents-complete-guide |
| `test_office_workspace_catalogs.py` | workspace-and-catalogs |
| `test_office_create_upload.py` | create-and-upload-documents |
| `test_office_explorer.py` | explorer-search-and-organize |
| `test_office_document_actions.py` | document-actions-move-rename-delete |
| `test_office_views_trash.py` | views-and-trash (recent + starred + deleted + purge) |
| `test_office_access_members.py` | catalog-access-and-members |
| `test_office_share_links.py` | share-catalog-and-document |
| `test_office_public_preview.py` | public-link-preview |
| `test_office_editor.py` | edit-in-onlyoffice, view-other-file-types |
| `test_office_rag.py` | catalog-rag-and-semantic-search |
| `test_office_mobile.py` | mobile-documents-workflow |

Helpers: `office_e2e_helpers.py`. API seed: `tests/office/access_helpers.py`, `tests/office/helpers.py`.
