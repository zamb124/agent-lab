# Mail tests

## Offline (CI, всегда)

```bash
uv run pytest -q tests/core/mail --ignore=tests/core/mail/live
```

Реальная shared Postgres + `RecordingMailServerPort` через DI (без сети к mail-серверу).

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

### Матрица

| Файл | Сценарии |
|---|---|
| `live/test_ispmanager_live.py` | health, ensure/list, loopback, A→B, ensure idempotent, roles, delete-deny |
| `live/test_mail_service_live.py` | system ensure, PUT forbidden, bind+send+fetch |
| `live/test_mail_scenarios_live.py` | attachments, unicode, reply headers, lazy bind, iMIP→calendar |

### Квота

- Только `plt-{unique_id}*@…`
- Role boxes: ensure only, never delete
- `mail_quota_sweeper` + per-test finally удаляют созданные адреса

### Shared hosting quirks

- Сервер может переписать `Message-Id` — live матчит по `Subject`
- IMAP FETCH body приходит как `bytearray` (учтено в transport)
