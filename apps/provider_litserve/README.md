# Реранкер и эмбеддер (LitServe, OpenAI-совместимый API)

**`provider_litserve` в `conf.json`** — контур **локальных** моделей: клиенты RAG (`rag.embedding` / `rag.reranker` с **`provider: provider_litserve`**) ходят на HTTP API LitServe. Инференс выполняется во **воркерах** LitServe (отдельные процессы на эндпоинты `/v1/embeddings` и `/v1/rerank`). Облачные эмбеддинги без своего стека — **`openrouter`** из **`llm`**, не этот блок.

Один процесс:

| Сервис (`scripts/run.py`) | Модуль | Порт (по умолчанию) | Зависимости |
|---------------------------|--------|---------------------|-------------|
| **`provider-litserve`** | **`apps.provider_litserve.main`** (LitServe) | **`provider_litserve.infra.gateway_port`** (8014) | **`uv sync --group reranker-model`** для реальных весов эмбеддера и `flagllm` |

**Маршруты** (один хост:порт):

- **GET** `/v1/models` — список моделей в форме OpenRouter (эмбеддинги, реранк и чат-модель).
- **POST** `/v1/chat/completions` — OpenAI-совместимый чат через встроенный `LitServe OpenAISpec` и локальную HF-модель.
- **POST** `/v1/embeddings` — OpenAI-совместимое тело; инференс во воркерах **`EmbeddingLitAPI`** ([`embedding/api.py`](embedding/api.py), движок [`embedding/engines.py`](embedding/engines.py)).
- **POST** `/v1/rerank` — тело `{query, passages}`; ответ `{scores}`; инференс во воркерах **`RerankerLitAPI`** ([`reranker/api.py`](reranker/api.py), движок [`reranker/engines.py`](reranker/engines.py)).
- **GET** `/health` — встроенный LitServe: текст **`ok`** / **`not ready`** (пока воркеры не готовы).

Контракты HTTP для OpenAPI и интеграционных тестов (in-process ASGI, те же `EmbeddingLitAPI` / `RerankerLitAPI`, без воркеров): [`provider_litserve_asgi.py`](provider_litserve_asgi.py), схемы ответов — [`provider_litserve_http_schemas.py`](provider_litserve_http_schemas.py); тела запросов POST — [`openai_server_contracts.py`](openai_server_contracts.py). Для чата в runtime используется встроенный `OpenAISpec` LitServe.

Общее: [`shared.py`](shared.py). Настройки: [`config.py`](config.py) — `get_provider_litserve_settings()` через `load_merged_config("provider_litserve")`.

**`EmbeddingService`** — **`POST …/v1/embeddings`**; **`RerankerHTTPClient`** (**`apps/rag/services/reranker_client.py`**) — **`…/v1/rerank`**.

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
    "backend": "placeholder",
    "model_id": "BAAI/bge-reranker-v2-gemma",
    "embedding_model_id": "BAAI/bge-m3",
    "embedding_openai_model_id": "baai/bge-m3",
    "rerank_openai_model_id": "baai/bge-reranker-v2-gemma",
    "llm_model_id": "Qwen/Qwen2.5-1.5B-Instruct",
    "embedding_model_ids": ["text-embedding-3-small"],
    "rerank_model_ids": [],
    "llm_model_ids": ["Qwen/Qwen2.5-1.5B-Instruct"]
  }
}
```

**`embedding_model_id`** — HuggingFace id весов; **`embedding_openai_model_id`** (и аналог **`rerank_openai_model_id`**) — имя поля `model` в OpenAI-совместимых запросах. Для одной пары весов не дублируйте в **`embedding_model_ids`** / **`rerank_model_ids`** тот же id в другом регистре: каждая уникальная строка `api_model_id` при первом сиде реестра ([`model_registry.py`](model_registry.py), SQLite `infra.sqlite_path`) даёт **отдельную** строку в UI «Model registry»; лишние алиасные строки = лишние карточки. Дополнительные модели — отдельные строки в списках (как `text-embedding-3-small` в примере).

Запросы **POST /v1/embeddings** и **POST /v1/rerank** принимают `model` без учёта регистра: значение сопоставляется с зарегистрированными идентификаторами (реестр + дефолты из конфига, пока каталог в памяти не загружен из БД).

Переопределение деплоя: **`services.provider_litserve`**. ENV: **`PROVIDER_LITSERVE__API__*`**, **`PROVIDER_LITSERVE__INFRA__*`** (например **`PROVIDER_LITSERVE__INFRA__MODEL_ID`**, **`PROVIDER_LITSERVE__INFRA__EMBEDDING_MODEL_ID`**, **`PROVIDER_LITSERVE__INFRA__GATEWAY_PORT`**).
Токен Hugging Face для скачивания приватных/ограниченных моделей: **`HF_TOKEN`** (env) или `services.provider_litserve.provider_litserve.infra.hf_token` в `conf.local.json`.

Пока runtime-каталог не поднят с SQLite, идентификаторы в **GET /v1/models** строятся из той же схемы, что сид **infra**: **`llm_model_ids`** / **`llm_model_id`**, пары **embedding** / **rerank** (дефолтные `*_openai_model_id` + списки **`embedding_model_ids`**, **`rerank_model_ids`**). После загрузки воркеров — из строк реестра с `status=ready`.

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
