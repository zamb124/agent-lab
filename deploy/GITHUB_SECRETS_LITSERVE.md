# GitHub Secrets для удалённого `provider_litserve`

Для удалённой ноды litserve нужен только отдельный хост; SSH берётся из тех же секретов, что и основной деплой (`SERVER_USER` и `SERVER_SSH_KEY`).

```bash
gh secret set LITSERVE_HOST -b"188.246.224.228" --repo OWNER/agent-lab
gh secret set PROVIDER_LITSERVE_API_BASE_URL -b"https://humanitec.ru/litserve/v1" --repo OWNER/agent-lab
```

`PROVIDER_LITSERVE_API_BASE_URL` можно удалить или задать пустым для режима локального контейнера `provider_litserve` на ноде A (`--profile litserve_local`).

Секреты `SERVER_HOST` и `POSTGRES_PASSWORD` уже используются основным деплоем; job `deploy-litserve` подставляет их же для строк подключения БД с ноды litserve к основному Postgres.

Откат на локальный litserve на ноде A: **`deploy/ROLLBACK_LITSERVE.md`**.
