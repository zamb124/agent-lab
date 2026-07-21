# Google API emulator contract

Stateful local stand-in for endpoints used by platform Google clients.
Response shapes follow Google REST samples (Sheets API v4 / Docs API v1 / Drive API v3).

## Surfaces

| Base (client setting) | Emulator path prefix | Spec |
|---|---|---|
| `sheets_base` → `.../v4` | `/v4/...` | https://developers.google.com/sheets/api/reference/rest/v4 |
| `docs_base` → `.../v1/documents` | `/v1/documents` | https://developers.google.com/docs/api/reference/rest/v1 |
| `drive_base` → `.../drive/v3` | `/drive/v3/...` | https://developers.google.com/drive/api/reference/rest/v3 |
| `drive_upload_base` | `/upload/drive/v3/files` | multipart upload |
| `token_uri` | `/token` | OAuth2 token for SA JWT bearer |

## Auth

`Authorization: Bearer <token>`. Valid tokens are registered on the emulator handle
(`oauth-user`, `sa-company` by default). Missing/invalid → 401 Google error envelope.
