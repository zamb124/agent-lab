# Multi-brand prod smoke (primary apex: linnex.io)

Выполнять после деплоя с `primary_platform_domain=linnex.io`.

## Infra

1. `bash deploy/scripts/setup-brand-dns.sh` — A records для linnex.io (`@`, `*`, `livekit`, `onlyoffice`, `grafana`, `cdn`, `api`).
2. `bash deploy/scripts/setup-wildcard-tls.sh` — SAN включает linnex.io и `*.linnex.io`.
3. `kubectl describe certificate platform-tls -n platform` — `Ready=True`.
4. `make k8s-deploy IMAGE_TAG=<sha>` и `make k8s-health CHECK_PUBLIC=1 PLATFORM_APEX_HOSTS="humanitec.ru linnex.io"`.

## OAuth providers

См. [oauth-multi-brand-checklist.md](./oauth-multi-brand-checklist.md): callbacks на **обоих** apex; Apple Service ID `app.linnex.io` как primary.

## Public API smoke

```bash
for apex in humanitec.ru linnex.io; do
  curl -fsS "https://${apex}/frontend/api/platform/brand" | jq -e ".base_domain == \"${apex}\""
done
curl -fsS -H 'Host: linnex.io' https://linnex.io/manifest.json | jq -e '.short_name == "Linnex"'
```

## End-to-end (manual)

1. Login на `https://linnex.io` (Yandex/Google/GitHub/Apple).
2. Tenant dashboard `https://{slug}.linnex.io`.
3. Embed snippet с linnex CDN origin.
4. Sync call — token `livekit_url` = `wss://livekit.linnex.io`.
5. Office document open — OnlyOffice `https://onlyoffice.linnex.io`.
6. HumanitecAgent download с `Host: linnex.io` → redirect на `https://linnex.io/...`.

## Legacy humanitec.ru

Повторить пункты 1–6 для `humanitec.ru` / `*.humanitec.ru` (regression).
