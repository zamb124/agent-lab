# Деплой Agent-Lab Platform

## Принцип

GitHub Actions собирает Docker-образ и пушит его в `ghcr.io`.
Потом по SSH заходит на сервер и перезапускает все сервисы с новым образом.

```
git push -> GitHub Actions -> ghcr.io -> SSH -> docker compose up -d
```

---

## Структура файлов

| Файл | Назначение |
|------|-----------|
| `Dockerfile` | Мульти-стейдж: agents, frontend, crm, rag, sync, worker, scheduler, rag-worker, sync-worker, migrations, full |
| `docker-compose-prod.yaml` | Все сервисы: postgres, redis, agents, frontend, crm, rag, sync, worker, scheduler, rag-worker, sync-worker, migrations |
| `.github/workflows/deploy.yml` | CI/CD пайплайн |
| `deploy/k8.sh` | Одноразовая подготовка сервера (MicroK8s + Docker Engine + Portainer) |
| `deploy/ingress.sh` | Настройка Ingress + cert-manager (Let's Encrypt) |
| `deploy/wildcard-tls.sh` | Wildcard сертификат `*.{domain}` через acme.sh + reg.ru DNS API |

---

## Первоначальная настройка (один раз)

### 1. Подготовить сервер

```bash
bash deploy/k8.sh
```

Устанавливает MicroK8s, Docker Engine, Portainer Agent и создаёт `/opt/agent-lab/.env`.

### 2. Настроить Ingress (SSL)

Добавить в `conf.local.json`:

```json
{
  "selectel": {
    "ip": "84.38.184.105",
    "login": "root",
    "ssh_port": "22"
  },
  "ingress": {
    "domain": "humanitec.ru",
    "email": "admin@humanitec.ru",
    "subdomains": [
      {"name": "sync", "port": 8005, "websocket": true},
      {"name": "agents", "port": 8001, "websocket": false},
      {"name": "crm", "port": 8003, "websocket": false},
      {"name": "rag", "port": 8004, "websocket": false}
    ]
  }
}
```

Запустить:

```bash
bash deploy/ingress.sh
```

### 3. Добавить секреты в GitHub

Settings -> Secrets and variables -> Actions:

| Секрет | Значение |
|--------|---------|
| `SERVER_HOST` | IP сервера |
| `SERVER_USER` | логин (root) |
| `SERVER_SSH_KEY` | приватный SSH-ключ |
| `GHCR_TOKEN` | Personal Access Token с `read:packages` |
| `POSTGRES_PASSWORD` | `openssl rand -hex 32` |
| `AUTH_JWT_SECRET` | `openssl rand -hex 32` |

### 4. Первый запуск

На сервере:

```bash
cd /opt/agent-lab
docker compose -f docker-compose-prod.yaml up -d postgres redis
sleep 5
docker compose -f docker-compose-prod.yaml run --rm migrations
docker compose -f docker-compose-prod.yaml up -d
```

---

## Как работает деплой

При каждом `git push` в `main`:

1. GitHub Actions собирает Docker-образ с тегом `sha-<commit>` и `latest`
2. Пушит в `ghcr.io/<username>/agent-lab`
3. Копирует `docker-compose-prod.yaml` на сервер в `/opt/agent-lab/`
4. По SSH: pull образов, миграции, рестарт всех сервисов

Postgres и Redis при этом **не перезапускаются**.

---

## Сервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| agents | 8001 | AI агенты, flows, skills |
| frontend | 8002 | Управление платформой, UI |
| crm | 8003 | CRM: entities, graph |
| rag | 8004 | RAG: документы, поиск |
| sync | 8005 | Инженерный чат, Git |
| worker | - | TaskIQ worker (agents) |
| scheduler | - | TaskIQ scheduler |
| rag-worker | - | TaskIQ worker (RAG) |
| sync-worker | - | TaskIQ worker (sync realtime) |

---

## Ручной деплой (без GitHub Actions)

```bash
docker build -t ghcr.io/<username>/agent-lab:latest --target full .
docker push ghcr.io/<username>/agent-lab:latest

ssh root@<SERVER_IP>
cd /opt/agent-lab
docker compose -f docker-compose-prod.yaml pull
docker compose -f docker-compose-prod.yaml run --rm migrations
docker compose -f docker-compose-prod.yaml up -d
```
