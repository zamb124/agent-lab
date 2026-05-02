# Откат provider_litserve на основной сервер (нода A)

Идемпотентный порядок без миграций БД и без смены образа.

1. **Ingress:** в локальном `conf.local.json` у записи `provider_litserve` в `ingress.services[]` удалите поле `upstream_host` (Endpoints снова указывают на IP хоста ноды A). Выполните `bash deploy/ingress.sh`.
2. **Платформа:** в GitHub Secrets удалите или очистите `PROVIDER_LITSERVE_API_BASE_URL` (чтобы в SSH-деплое не экспортировался URL через секрет). Запустите workflow Deploy — контейнеры возьмут дефолт `http://provider_litserve:8014/v1` из `docker-compose-prod.yaml`.
3. **Локальный litserve на A:** на сервере `84.38.184.105`:
   ```bash
   cd /opt/agent-lab
   docker compose -f docker-compose-prod.yaml --profile litserve_local up -d provider_litserve
   ```
4. **Нода litserve:** на `188.246.224.228`:
   ```bash
   cd /opt/agent-lab
   docker compose -f docker-compose-litserve.yaml down
   ```
   Том `provider_litserve_hf_cache` сохраняется для возможного повторного включения удалённого режима.

5. **Фаервол (опционально):** на ноде A снимите правила `ufw` для IP ноды litserve к портам `5432`/`6379`, если удалённый режим больше не используется.

Проверка: `curl -fsS https://humanitec.ru/litserve/health`, загрузка документа в RAG и семантический поиск без ошибок в логах `rag_worker`.
