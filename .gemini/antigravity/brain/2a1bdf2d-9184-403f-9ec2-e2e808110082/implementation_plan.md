# Архитектурный план миграции на полноценный Kubernetes (MicroK8s) кластер

Переход от гибридной инфраструктуры (Docker Compose + MicroK8s Ingress) к полноценному и "правильному" Kubernetes кластеру. Это устранит зоопарк скриптов (`bootstrap-litserve-node.sh`, ручные пробросы через `ufw`, отдельные `docker-compose-litserve.yaml`) и сделает деплой полностью унифицированным и готовым к масштабированию (добавлению новых физических нод).

## User Review Required

> [!IMPORTANT]
> **Перенос данных Postgres и Redis:** 
> Текущие данные хранятся в Docker volumes на основном сервере. При переносе в Kubernetes (StatefulSet) потребуется аккуратно скопировать файлы данных (или сделать pg_dump/pg_restore) в новый PersistentVolume.

> [!CAUTION]
> **Сетевая связность серверов:** 
> Для объединения серверов в один кластер MicroK8s они должны "видеть" друг друга по сети (открытые порты для k8s API, Calico/Flannel CNI). Мы настроим файрвол (`ufw`), чтобы разрешить трафик между IP `84.38.184.105` и `188.246.224.228`.

## Open Questions

> [!WARNING]
> 1. **Хранилище данных (Storage):** Сейчас базы лежат на диске первой ноды. Хотите ли вы оставить привязку баз данных строго к первой ноде (используя `hostPath` или `local-path-provisioner` с `nodeAffinity`), или развернуть распределенное хранилище вроде Longhorn/OpenEBS Mayastor (чтобы данные реплицировались между нодами)? *Рекомендую для начала оставить привязку к первой ноде для надежности Postgres, так как вторая нода специфична под GPU.*
> 2. **Управление конфигурацией:** Для описания инфраструктуры в K8s будем использовать Helm-чарты или сырые YAML-манифесты (Kustomize)? *Рекомендую Helm для удобного управления переменными окружения из GitHub Actions.*
> 3. **NVIDIA Драйверы:** На втором сервере (188.246.224.228) уже установлены проприетарные драйверы NVIDIA на уровне ОС Ubuntu? MicroK8s потребуется аддон `gpu` для проброса карточек в поды.

## Proposed Changes

Архитектура 2026 года для вашего кластера:

### 1. Топология кластера
- **Master Node (84.38.184.105):** Control plane, базы данных, frontend, основные агенты, CRM, фоновые воркеры.
- **GPU Worker Node (188.246.224.228):** Присоединяется к мастеру командой `microk8s add-node`. На ней с помощью Kubernetes `nodeSelector` (например, `node-role=gpu-worker`) будет автоматически запускаться под `provider_litserve`. 

### 2. Замена Docker Compose на Kubernetes Deployments
Все 15+ сервисов из `docker-compose-prod.yaml` описываются как стандартные Kubernetes сущности:
- **StatefulSets:** `postgres`, `redis`, `loki`, `tempo`, `grafana` (с Persistent Volume Claims).
- **Deployments:** `frontend`, `agents`, `crm`, `rag`, `sync`, `office`, воркеры (`flows_worker`, `scheduler`, и т.д.).
- **DaemonSet:** `alloy` (будет бежать на **каждой** ноде кластера, чтобы собирать логи со всех подов, включая GPU ноду).

Образ для всех сервисов останется **абсолютно одинаковым** (`ghcr.io/zamb124/agent-lab:latest`), меняется только команда запуска внутри Deployment, как это было в Compose.

### 3. Интеграция `provider_litserve`
Больше никаких костылей с `ufw allow 5432` и публичными IP. 
В манифесте K8s для `provider_litserve` мы укажем:
```yaml
nodeSelector:
  accelerator: nvidia-gpu
```
Kubernetes сам скачает образ на вторую ноду, запустит контейнер с доступом к GPU и соединит его с `postgres` и `redis` через внутреннюю защищенную сеть K8s (`postgres.default.svc.cluster.local`).

### 4. Ingress и Роутинг
Текущий `deploy/ingress.sh` сильно упростится.
Вместо ручного создания `Endpoints` на `HOST_IP` и костылей, K8s Ingress Controller будет напрямую роутить трафик в поды (`ClusterIP` сервисы). Сертификаты (`cert-manager`) продолжат работать как раньше.

### 5. CI/CD (GitHub Actions)
Вместо копирования `docker-compose.yaml` по SSH, CI/CD будет:
1. Собирать образ и пушить в GHCR (как сейчас).
2. Вызывать `kubectl set image deployment/xxx xxx=ghcr.io/...` или `helm upgrade` через защищенный `kubeconfig`.
Никакого ручного SSH.

## Verification Plan

### Manual Verification
1. Зайти по SSH на Master ноду. Сгенерировать токен `microk8s add-node`.
2. Зайти по SSH на Worker ноду. Установить microk8s и сделать `microk8s join`.
3. Убедиться, что `microk8s kubectl get nodes` показывает обе ноды в статусе Ready.
4. Накатить Helm-чарт со всеми сервисами.
5. Проверить, что под `litserve` запланировался именно на второй ноде (`kubectl get pods -o wide`).
6. Убедиться, что логи с обеих нод собираются в единую Grafana (с помощью DaemonSet Alloy).
7. Провести UI-тестирование, чтобы убедиться, что всё работает (RAG, загрузка документов, логин).
