# RAG Service

Микросервис управления документами и поиска (RAG): REST API под **`/rag/api/v1/`**, UI в **`apps/rag/ui/`** (Lit 3, EventBus + фабрики), порт **8004**.

Подробные инварианты конфигурации, провайдеров и индексации — **`.cursor/rules/rag.mdc`**. Каскад настроек платформы — **`configuration.mdc`**.

## Принципы

- **Провайдер** (`pgvector`, `agentset`) определяет хранение чанков и способ поиска. У namespace фиксируется провайдер создания. В запросах к API опционально передаётся **`?provider=`**; иначе используется **`rag.default_provider`** из конфигурации.
- **Индексация асинхронная**: загрузка файла возвращает **202** и идентификатор фоновой задачи; итог смотрите по **`GET /rag/api/v1/documents/{document_id}/status`**. Для выполнения задач должен быть запущен **rag_worker** (TaskIQ).
- **Межсервисные вызовы** к RAG — через **`RagClient`** (`core/clients/rag_client.py`) поверх **`ServiceClient`** (сервис `"rag"`), с контекстом **`get_context()`**, не прямым `httpx` между сервисами.
- **Префикс API** — только **`/rag/api/v1/...`**.

## HTTP-контракт

### Провайдеры

| Метод | Путь |
|-------|------|
| GET | `/rag/api/v1/providers` |
| POST | `/rag/api/v1/providers/switch` — тело: `{ "provider_name": "<имя>" }` |

### Namespaces

| Метод | Путь |
|-------|------|
| GET | `/rag/api/v1/namespaces` |
| POST | `/rag/api/v1/namespaces` — тело: `name`, `description`; опционально `?provider=` |
| DELETE | `/rag/api/v1/namespaces/{namespace_id}` — опционально `?provider=` |

Ответ списка включает **`namespaces`** и агрегат **`document_status_counts_by_namespace`** (счётчики по статусам обработки документов).

### Документы

| Метод | Путь |
|-------|------|
| GET | `/rag/api/v1/namespaces/{namespace_id}/documents` — список документов и сводка (**summary**: чанки, счётчики по статусам); опционально `?provider=` |
| POST | `/rag/api/v1/namespaces/{namespace_id}/documents` — **multipart**: поле файла **`file`**, опционально **`metadata`** (JSON-строка). Ответ **202** (принятие в очередь). Опционально `?provider=` |
| DELETE | `/rag/api/v1/namespaces/{namespace_id}/documents/{document_id}` — опционально `?provider=` |
| GET | `/rag/api/v1/documents/{document_id}/status` — статус индексации |

Не смешивать загрузку **multipart** с телом **`application/json`** вместо поля `metadata`: для файла используется `FormData` с JSON внутри **`metadata`**.

### Поиск

| Метод | Путь |
|-------|------|
| POST | `/rag/api/v1/namespaces/{namespace_id}/search` — опционально `?provider=` |
| POST | `/rag/api/v1/search` — поиск сразу по нескольким namespace (в теле **`namespace_ids`**); опционально `?provider=` |

**Тело запроса поиска** (`SearchRequest`):

- **`query`** (обязательно), **`limit`** (по умолчанию 5).
- **`filters`** — опционально, фильтрация по метаданным.
- **`channels`** — `{ "semantic": bool, "lexical": bool }`; должен быть включён хотя бы один канал. Оба включены — fusion (RRF) у pgvector; только semantic — вектор; только lexical — полнотекст.
- **`rrf_k`**, **`per_channel_top_k`**, **`rerank`** — опционально.
- Не заданные в запросе поля могут заполняться из **`rag.document_indexing.search_defaults`** в конфигурации.

**Ответ**: **`results`** (список `RAGSearchResult`), **`query`**, **`namespace_id`** (для single-namespace), **`provider`**.

**Ограничение**: провайдер **Agentset** не поддерживает лексический канал в комбинациях, которые требуют FTS; запрос с лексикой там приведёт к **400**. Ошибки реранкера не подавляются.

## Настройки

| Уровень | Назначение |
|---------|------------|
| **Глобальный конфиг** (`conf.json` / `conf.local.json`, приоритет у ENV) | **`rag.embedding`** — одна модель эмбеддингов на контур; **`rag.reranker`** — реранк после retrieve; **`rag.document_indexing`** — профиль индексации (split, parsing, lexical, опционально **`search_defaults`**); **`rag.providers.*`** — параметры провайдеров. |
| **Загрузка документа** | В **`metadata`** можно передать **`index_profile_config`** (частичный оверлей к глобальному профилю), например **`split`**, **`parsing`** — глубокое слияние на стороне воркера/API. |

## UI (`apps/rag/ui/`)

- **Состояние и HTTP**: фабрики в **`apps/rag/ui/events/resources/*.resource.js`** (`rag/namespaces`, `rag/documents`, `rag/search`, `rag/document_upload`, …) с REST mirror на эндпоинты выше.
- **Счётчики документов** на карточке namespace берутся из **`document_status_counts_by_namespace`**.
- **Маршрутизация**: `createRouterEffect` — `namespaces`, `namespace_detail`, `search`, `settings` (см. **`rag.mdc`**).
- Канон фронтенда платформы — **`frontend.mdc`**, **`ui_factories.mdc`**.

## Flows: ресурс `RAGResource`

В графах flow ресурс **`RAGResource`** (`apps/flows/src/resources/wrappers/rag_resource.py`):

- **Поиск** — **`RAGRepository.search_namespace`** (`core/rag/repository.py`) через **`ServiceClient`** → **`POST /rag/api/v1/namespaces/{namespace_id}/search`**. Дефолты **`namespace`**, **`provider`**, **`default_top_k`**, **`company_id`**, **`search_options`** — из **`RagResourceBindParams`** (`core/rag/rag_resource_bind.py`); те же поля у **`core.rag.rag_resource.RAGResource`** в интеграционных сценариях.
- **Загрузка текста** (`add_document`) — in-process **`RAGRepository.provider.upload_document_from_text`**.

Параметры конфига: **`namespace`**, **`provider`**, **`default_top_k`**, опционально **`company_id`**, **`search_options`** и **`index_profile_config`**.

**`RAGRepository`** (`core/rag/repository.py`): in-process **`provider`** (на контейнере — pgvector, см. **`RAG_IN_PROCESS_PROVIDER_ID`** в `core/rag/constants.py`) и опционально **`service_client`** + **`bind`** для HTTP **`search_namespace`** (тот же контракт, что **`POST /rag/api/v1/namespaces/{id}/search`**). Постановка индексации из API и воркера — напрямую через TaskIQ-задачи в `apps/rag_worker/tasks/` и вызовы из `apps/rag/api/`.

Единая сборка path/body для HTTP-поиска по namespace — **`core/rag/rag_http_namespace_search.py`** (используют **`RagClient.search`** и **`RAGRepository.search_namespace`**).

Результат **`RAGResource.search`** — список словарей: **`content`**, **`score`**, **`document_id`**, **`metadata`**.

## Структура каталога

```
apps/rag/
├── main.py
├── config.py
├── container.py
├── dependencies.py
├── api/
│   ├── providers.py
│   ├── namespaces.py
│   ├── documents.py
│   └── search.py
├── services/
└── ui/
    ├── index.html
    ├── index.js
    ├── app/rag-app.js
    ├── components/
    ├── modals/
    ├── pages/
    └── events/resources/
```

Реранк после retrieve: **`core/rag/post_retrieval_rerank.py`**.

## Запуск

Локально (из корня репозитория):

```bash
uv run python scripts/run.py rag
```

Сервис: **`http://localhost:8004`**. UI: **`http://localhost:8004/rag/ui`**.

Полный стек разработки: **`make app`** (см. корневой README / `scripts/run.py`).

Для индексации документов дополнительно запускайте **rag-worker**: `uv run python scripts/run.py rag-worker` (или через цели в `Makefile`, если описаны).

## Пример вызовов

```bash
curl -s http://localhost:8004/rag/api/v1/providers

curl -s http://localhost:8004/rag/api/v1/namespaces

curl -s -X POST http://localhost:8004/rag/api/v1/namespaces/{namespace_id}/search \
  -H "Content-Type: application/json" \
  -d '{"query":"текст запроса","limit":5,"channels":{"semantic":true,"lexical":true}}'
```

## Прямое использование провайдера в коде (тот же контракт поиска)

```python
from core.rag.factory import get_rag_provider

provider = get_rag_provider("pgvector")
results = await provider.search(
    namespace_id="my_namespace",
    query="Пример",
    limit=5,
)
```

## Устранение неполадок

- **Документ в очереди / не индексируется** — проверьте процесс **rag_worker** и логи задач TaskIQ.
- **Pgvector** — доступность БД RAG и миграции схемы (см. **`migrations.mdc`**).
- **Agentset** — корректность **`api_key`** и **`base_url`** в **`rag.providers.agentset`**.
- **Реранк / эмбеддинги** — см. **`rag.embedding`**, **`rag.reranker`** и при **`provider: provider_litserve`** — **`provider_litserve`** и **`apps/provider_litserve/README.md`**.
