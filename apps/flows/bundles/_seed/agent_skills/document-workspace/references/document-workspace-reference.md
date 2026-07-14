# document-workspace — call examples

## create_file (markdown → docx)

```json
{
  "content": "# Report\n\n| Col | Value |\n| --- | --- |\n| A | 1 |",
  "original_name": "report.docx",
  "content_mode": "markdown"
}
```

## documents_open_file

```json
{ "file_id": "<from create_file or state.files>" }
```

## documents_append_text

```json
{
  "file_id": "<id>",
  "text": "\n\n## Follow-up\n\nDone."
}
```
