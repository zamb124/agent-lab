# Mail tests

## Offline (CI, всегда)

```bash
uv run pytest -q tests/core/mail --ignore=tests/core/mail/live
```

Реальная shared Postgres + `RecordingMailServerPort` через DI (без сети к mail-серверу).

### Матрица complete mail client (offline)

| Домен | Файл | Покрытие |
|---|---|---|
| Sync | `test_mail_complete_client_sync.py` | bootstrap; incremental; UIDVALIDITY wipe; backfill `oldest_uid`/`backfill_completed`; reconcile orphans; flag refresh; `request_sync_now` |
| Mutations | `test_mail_complete_client_mutations.py` | move/trash/archive/delete; star/unstar; draft APPEND+replace; `prepare_send_local` temp uid; send + sync enqueue |
| Search | `test_mail_complete_client_search.py` | cursor pages disjoint; subject/body/from; folder scope; `needs_sync` empty list |
| Role | `test_mail_complete_client_role.py` | role bind; members add/remove; member ACL; outsider deny; admin access; `list_my_bindings`; RAG ns `mail-{mailbox_binding_id}` |
| IDLE | `test_mail_complete_client_idle.py` | EXISTS → enqueue sync; TIMEOUT no enqueue; `idle_enabled=false` |
| HTTP API | `test_mail_complete_client_api.py` | `/sync`, search, trash/archive/delete/star/move, drafts, members |
| TaskIQ | `test_mail_complete_client_taskiq.py` | `mail_trash`/`mail_star` IMAP calls; `mail_send` → `send_failed` push |

Helpers: `complete_client_helpers.py` (`seed_connected_user_binding`, `STANDARD_FOLDERS`).

## Frontend

```bash
npx vitest run tests/frontend_core/unit/reducers/mail.spec.js tests/frontend_core/unit/effects/mail.effect.spec.js
uv run pytest tests/ui/design-system/components/platform-mail-modal/playwright.spec.py -v
```

| Слой | Покрытие |
|---|---|
| Reducer | SYNC_*, APPEND, trash/archive/star, moved/removed, send_succeeded/failed, binding members |
| Effect | sync, search, load-more, trash/archive/star, members load |
| Playwright L2 | modal mount + search/refresh/triage/role badge smoke |

## Креды

Секреты **только** в `conf.local.json` (gitignored) или ENV `MAIL__*`.

### Локально — `conf.local.json`

```json
{
  "mail": {
    "system": {
      "enabled": true,
      "mail_domain": "linnex.io",
      "provider": "ispmanager",
      "imap_host": "sm36.hosting.reg.ru",
      "imap_port": 993,
      "smtp_host": "sm36.hosting.reg.ru",
      "smtp_port": 465,
      "use_ssl": true,
      "ispmanager": {
        "base_url": "https://sm36.hosting.reg.ru:1500/ispmgr",
        "authinfo_user": "YOUR_USER",
        "authinfo_password": "YOUR_PASSWORD"
      }
    },
    "live_test": {
      "enabled": true,
      "mailbox_prefix": "plt-",
      "allow_delete": true
    }
  }
}
```

`imap_host`/`smtp_host` = hostname панели ISPmanager.  
`mail.linnex.io` сейчас указывает на IP платформы — для IMAP/SMTP не использовать, пока DNS/MX не укажут на mail-сервер.

### GitHub Actions Secrets

| Secret | Значение |
|---|---|
| `MAIL_ISPMANAGER_BASE_URL` | `https://…:1500/ispmgr` |
| `MAIL_ISPMANAGER_AUTHINFO_USER` | логин панели |
| `MAIL_ISPMANAGER_AUTHINFO_PASSWORD` | пароль панели |

ENV: `MAIL__SYSTEM__ISPMANAGER__*` + `MAIL__LIVE_TEST__ENABLED=true` + hosts (см. `.github/workflows/mail-live.yml`).

## Live

```bash
uv run pytest -q tests/core/mail/live -m network --tb=short -n0
```

**VPN:** исходящий SMTP `:465` часто режется VPN — отключи VPN или гоняй с VPS. Проверка: `nc -vz sm36.hosting.reg.ru 465`.

### Матрица live

| Файл | Сценарии |
|---|---|
| `live/test_ispmanager_live.py` | health, ensure/list, loopback, A→B, ensure idempotent, roles, delete-deny |
| `live/test_mail_service_live.py` | system ensure, PUT forbidden, bind+send+fetch |
| `live/test_mail_scenarios_live.py` | attachments, unicode, reply headers, lazy bind, iMIP→calendar |
| `live/test_mail_complete_client_live.py` | provision+sync; send A→B; star/trash; drafts; search; sync-now; role ACL; local wipe+resync |

### Квота

- Только `plt-{unique_id}*@…`
- System role boxes: ensure only, never delete
- `mail_quota_sweeper` + per-test finally удаляют созданные адреса

### Shared hosting quirks

- Сервер может переписать `Message-Id` — live матчит по `Subject`
- IMAP FETCH body приходит как `bytearray` (учтено в transport)
