---
name: google-sheets
description: Read and write Google Sheets via spreadsheet_id and A1 ranges. Use when the user mentions Google Sheets, spreadsheets URLs, append/update rows, or tabs.
allowed-tools: sheets_create_spreadsheet sheets_get_metadata sheets_list_sheets sheets_get_values sheets_batch_get_values sheets_update_values sheets_batch_update_values sheets_append_rows sheets_clear_values sheets_batch_clear_values sheets_share sheets_add_sheet sheets_rename_sheet sheets_delete_sheet
---

# Google Sheets

## Goal

Read and write Google Spreadsheets with platform `sheets_*` tools after user Connect Google (`service=workspace`) or company/system Service Account.

## Procedure

1. Extract `spreadsheet_id` from URL `https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit`. Do not invent IDs.
2. Prefer `sheets_get_metadata` / `sheets_list_sheets` before destructive edits.
3. Read: `sheets_get_values` / `sheets_batch_get_values` with A1 ranges (`Sheet1!A1:C10`, quote titles with spaces: `'My Sheet'!A:A`).
4. Write:
   - `sheets_update_values` — overwrite a known range.
   - `sheets_append_rows` — append after the logical table found in `range` (values.append). Default `USER_ENTERED` and `INSERT_ROWS`.
5. Clear only when the user explicitly asks: `sheets_clear_values` / `sheets_batch_clear_values`.
6. Tabs: `sheets_add_sheet` / `sheets_rename_sheet` / `sheets_delete_sheet` (`sheet_id` from metadata).
7. Share: `sheets_share` with `email` or `anyone=true`.

## Notes

- `values.append` logical table ≠ Google Sheets **Tables** API (`addTable` / `tableId`). Use `sheets_*` values tools for normal ranges.
- Protected ranges may fail with Google API errors — report the error; do not invent workarounds.
- Auth: user **Connect Google** (one OAuth for Docs+Sheets), company admin SA, or variables `google_service_account` / `google_access_token` / `google_impersonate_email`.
