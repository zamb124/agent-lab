# Локальные модели LitServe

**`provider_litserve` в `conf.json`** — контур **локальных не-LLM моделей**: RAG использует эмбеддер и реранкер (`rag.embedding` / `rag.reranker` с **`provider: provider_litserve`**), voice-контур использует отдельные STT/TTS/VAD endpoints. Облачные эмбеддинги без своего стека — **`openrouter`** из **`llm`**, не этот блок.

Один процесс:

| Сервис (`scripts/run.py`) | Модуль | Порт (по умолчанию) | Зависимости |
|---------------------------|--------|---------------------|-------------|
| **`provider-litserve`** | **`apps.provider_litserve.main`** (LitServe) | **`provider_litserve.infra.gateway_port`** (8014) | **`uv sync --group reranker-model`** для реальных весов эмбеддера и `flagllm` |

**Маршруты** (один хост:порт):

- **GET** `/v1/models` — список локальных моделей в форме OpenRouter.
- **POST** `/v1/embeddings` — OpenAI-совместимое тело; инференс во воркерах **`EmbeddingLitAPI`** ([`embedding/api.py`](embedding/api.py), движок [`embedding/engines.py`](embedding/engines.py)).
- **POST** `/v1/rerank` — тело `{query, passages}`; ответ `{scores}`; инференс во воркерах **`RerankerLitAPI`** ([`reranker/api.py`](reranker/api.py), движок [`reranker/engines.py`](reranker/engines.py)).
- **POST** `/v1/audio/transcriptions` — локальный STT для voice-контуров.
- **POST** `/v1/audio/speech` — локальный TTS для voice-контуров.
- **POST** `/v1/audio/vad` — локальный VAD для voice-контуров.

LLM-моделей и Markdown endpoint в `provider_litserve` нет. Markdown форматируется общим `TextTransformService` через company capability `llm_format_markdown` и платформенный `get_llm()`.

- **GET** `/health` — базовая доступность ASGI-процесса.
- **GET** `/v1/health/inference` — готовность LitServe runtime и CUDA, если `accelerator`/`embedding_accelerator`/`rerank_accelerator` требуют GPU. Именно этот endpoint используется Kubernetes readiness/startup probe.

Контракты HTTP для OpenAPI и интеграционных тестов (in-process ASGI, те же `EmbeddingLitAPI` / `RerankerLitAPI`, без воркеров): [`provider_litserve_asgi.py`](provider_litserve_asgi.py), схемы ответов — [`provider_litserve_http_schemas.py`](provider_litserve_http_schemas.py); тела запросов POST — [`openai_server_contracts.py`](openai_server_contracts.py).

Общее: [`shared.py`](shared.py). Настройки: [`config.py`](config.py) — `get_provider_litserve_settings()` через `load_merged_config("provider_litserve")`.

**`EmbeddingService`** — **`POST …/v1/embeddings`**; **`RerankerHTTPClient`** (**`core/rag/post_retrieval_rerank.py`**) — **`…/v1/rerank`**.

Клиенты платформы задают **`provider_litserve.api.base_url`** (корень **`…/v1`**). Порт слушателя — **`provider_litserve.infra.gateway_port`** (не путать с **`rag.reranker`** в доменном смысле).

## Конфигурация

В **`conf.json`** один блок **`provider_litserve`**:

```json
"provider_litserve": {
  "api": {
    "base_url": "http://127.0.0.1:8014/v1"
  },
  "infra": {
    "gateway_port": 8014,
    "backend": "flagllm",
    "model_id": "Qwen/Qwen3-Reranker-0.6B",
    "embedding_model_id": "Qwen/Qwen3-Embedding-0.6B",
    "embedding_openai_model_id": "qwen/qwen3-embedding-0.6b",
    "rerank_openai_model_id": "qwen/qwen3-reranker-0.6b",
    "embedding_model_ids": [],
    "rerank_model_ids": []
  }
}
```

**`embedding_model_id`** — HuggingFace id весов; **`embedding_openai_model_id`** (и аналог **`rerank_openai_model_id`**) — имя поля `model` в OpenAI-совместимых запросах. Для одной пары весов не дублируйте в **`embedding_model_ids`** / **`rerank_model_ids`** тот же id в другом регистре: каждая уникальная строка `api_model_id` при первом сиде реестра ([`model_registry.py`](model_registry.py), SQLite `infra.sqlite_path`) даёт **отдельную** строку в UI «Model registry»; лишние алиасные строки = лишние карточки. Дополнительные модели — отдельные строки в списках.

Запросы **POST /v1/embeddings** и **POST /v1/rerank** принимают `model` без учёта регистра: значение сопоставляется с зарегистрированными идентификаторами (реестр + дефолты из конфига, пока каталог в памяти не загружен из БД).

Переопределение деплоя: **`services.provider_litserve`**. ENV: **`PROVIDER_LITSERVE__API__*`**, **`PROVIDER_LITSERVE__INFRA__*`** (в т.ч. **`PROVIDER_LITSERVE__INFRA__MODEL_ID`**, **`PROVIDER_LITSERVE__INFRA__EMBEDDING_MODEL_ID`**, **`PROVIDER_LITSERVE__INFRA__GATEWAY_PORT`**, **`PROVIDER_LITSERVE__INFRA__ACCELERATOR`** со значением `auto`, `cuda`, `cpu` или `mps`, **`PROVIDER_LITSERVE__INFRA__EMBEDDING_ACCELERATOR`** и **`PROVIDER_LITSERVE__INFRA__RERANK_ACCELERATOR`** для раздельного выбора устройства эмбеддера и реранкера).

## GPU на отдельной ноде кластера

`provider_litserve` запускается единственным подом на GPU-ноде MicroK8s через `nodeSelector: accelerator=nvidia-gpu` и `resources.limits."nvidia.com/gpu": 1`. Manifest — [**`deploy/helm/agent-lab/templates/50-gpu/litserve.yaml`**](../../deploy/helm/agent-lab/templates/50-gpu/litserve.yaml). Образ тот же, что у всей платформы (`ghcr.io/zamb124/agent-lab:latest`), команда `python -m apps.provider_litserve.main`.

Доступ к Postgres/Redis — через ClusterIP `postgres.platform.svc.cluster.local:5432` / `redis.platform.svc.cluster.local:6379` (никаких `ufw allow` или публичных пробросов). Доступ от других сервисов кластера — через ClusterIP `provider-litserve.platform.svc.cluster.local:8014` (env **`PROVIDER_LITSERVE__API__BASE_URL=http://provider-litserve:8014/v1`** задано в `templates/_helpers.tpl::agentlab.appEnv`). Внешний URL: `https://humanitec.ru/litserve/*` через основной Ingress.

На GPU-ноде должны быть установлены **проприетарный драйвер NVIDIA** и **`nvidia-container-toolkit`**. MicroK8s ставится одним аддоном `microk8s enable gpu` (NVIDIA Device Plugin). Лейбл ноды: `kubectl label node <gpu-node> accelerator=nvidia-gpu`. Шаги — в [**`deploy/cluster-setup.md`**](../../deploy/cluster-setup.md).

При **`accelerator`** = **`auto`** воркеры выберут **`cuda:0`**, только если **`torch.cuda.is_available()`** в контейнере; без настроенного GPU PyTorch упадёт с явным `RuntimeError` при попытке грузить модель на CUDA (не скрытый fallback на CPU).
Токен Hugging Face для скачивания приватных/ограниченных моделей: ключ **`hf-token`** в Kubernetes Secret **`platform-secrets`** (env **`HF_TOKEN`** в Pod), либо `services.provider_litserve.provider_litserve.infra.hf_token` в локальном `conf.local.json` для разработки.

Кэш моделей переживает рестарт пода — PVC `litserve-model-cache` (50Gi) на GPU-ноде, монтируется в `/root/.cache/huggingface`.

Пока runtime-каталог не поднят с SQLite, идентификаторы в **GET /v1/models** строятся из той же схемы, что сид **infra**: пары **embedding** / **rerank** (дефолтные `*_openai_model_id` + списки **`embedding_model_ids`**, **`rerank_model_ids`**). После загрузки воркеров — из строк реестра с `status=ready`.

## Сценарии

- Локально: **`uv sync --group reranker-model`** для **`sentence-transformers`** и **`flagllm`**; **`placeholder`** для реранкера допускает работу без тяжёлых весов реранка (эмбеддинги при первом вызове всё равно потребуют группу **`reranker-model`**, если нужны реальные вектора).

## Проверка

```bash
curl -sS http://127.0.0.1:8014/health
curl -sS http://127.0.0.1:8014/v1/models
```

**`provider_litserve.api.base_url`** должен указывать на **`gateway_port`**.

## Зависимости

Группа **`rag`**; тяжёлые модели — **`uv sync --group reranker-model`**.
