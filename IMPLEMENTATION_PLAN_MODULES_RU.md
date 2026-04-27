# План реализации по остаткам архитектуры (gap-driven)

Этот документ — **рабочий план “что ещё осталось сделать”** в репозитории относительно
`TARGET_ARCHITECTURE_RU (2).md` (архитектурный контракт).

Фокус плана: закрыть архитектурные разрывы, которые мешают **deep search**:
frontier/скоринг/релевантность/остановка, extraction+diff, run-level артефакты и настоящий restore-mode.

## 1) Как читать план

Для каждого блока:
- `Ссылка на справочник`: разделы `TARGET_ARCHITECTURE_RU (2).md`.
- `Что добавляем/меняем`: конкретные сущности и поведение.
- `Критерии готовности`: проверяемые условия (DoD).
- `Тесты`: минимальный набор.

## 2) Что уже сделано (опорная база)

Эти части считаем существующими и используем как фундамент:
- **Runtime ядро**: `CDPConnectionPool`, `PageLeaseManager`, `PlaywrightBrowserInteractor`, `BrowserRuntimeFacade`.
- **Control API + MCP**: HTTP `/control/*` и JSON-RPC MCP `/mcp`.
- **Session-level артефакты control**: `sessions/<session_id>/events/*.json` + sidecars.

Задача плана ниже — превратить runtime/control в полноценный **deep-search pipeline** на run-уровне.

---

## 3) Блок A — Настоящий restore-mode (session continuity)

**Ссылка на справочник:** `§5.2`, `§17`, `§31`  
**Приоритет:** P0 (блокирует pause/resume, долгие run, экономию ресурсов)

### Что добавляем/меняем

- Поддержать `restore_state_key` в `acquire()`:
  - создание BrowserContext с применением `storage_state` из `SessionStateStore`;
  - восстановление sessionStorage (уже есть) + корректная последовательность “создали контекст → открыли страницу → применили sessionStorage”.
- Довести `SessionStateStore` до минимального набора восстановления:
  - `current_url` (последний URL), `last_snapshot_ref` (если есть),
  - runtime flags, которые реально влияют на контекст (прокси/ua/locale/timezone/tier).
- Ввести run/session-level понятие TTL паузы:
  - soft/hard TTL политики на стороне будущего run orchestration (пока достаточно контракта и хранения).

### Критерии готовности

- Сценарий: `create_session(warm) → navigate → save_state → close_session → create_session(restore_state_key=...) → navigate/observe`:
  - cookies/localStorage восстанавливаются (через Playwright `storage_state`);
  - sessionStorage восстанавливается на нужном origin;
  - повторный заход видит “сессию” (например логин) без ручного ввода.
- `restore_state_key` — чистый контракт: неизвестный ключ → `KeyError` (без фолбеков).

### Тесты

- Integration: восстановление `storage_state` на живом endpoint.
- Unit: `SessionStateStore` структура blob, key lifecycle.

---

## 4) Блок B — Run-level артефакты и событийный лог (не per-session)

**Ссылка на справочник:** `§10`, `§16`, `§32`  
**Приоритет:** P0 (нужен для реплея/дебага/метрик/stop-signals)

### Что добавляем/меняем

- Ввести **run artifacts** (отдельно от текущих session artifacts):
  - `runs/<run_id>/manifest.json`,
  - `runs/<run_id>/events.ndjson`,
  - `runs/<run_id>/pages/<page_id>/...` (сырьё/clean/snapshot/diff/screen/pdf),
  - `runs/<run_id>/browser-trace/` (timeline.* + steps/*) — минимально в debug-режиме.
- Событийная модель `events.ndjson`:
  - минимально: `TASK_DEQUEUED`, `BROWSER_ACQUIRED`, `FETCH_DONE`, `EXTRACT_DONE`, `INGEST_DONE`, `TASK_DONE`, `TASK_FAILED`.
- `manifest.json` должен включать:
  - `run_id`, `mode`, timestamps, limits, stats, `artifacts_root`.

### Критерии готовности

- Любой run имеет воспроизводимый “след”: по `events.ndjson` можно понять, что происходило, и найти артефакты страниц.
- Артефакты не зависят от того, вызывали ли мы control API напрямую (crawler/agent пишут одинаково).

### Тесты

- Unit: schema/валидация manifest и event-record.
- Integration: один run пишет валидный каталог артефактов.

---

## 5) Блок C — Frontier + visited + URL scoring (скоринг самого поиска)

**Ссылка на справочник:** `§7.2`, `§19`, `§22.3`  
**Приоритет:** P0 (это “двигатель” deep search)

### Что добавляем/меняем

- `FrontierManager` (первый шаг — in-memory; следующий — Redis-backed):
  - priority queue по ключу `(score, depth, ts, url_norm)`;
  - visited set в скоупе `run_id`;
  - строгая нормализация URL (`url_norm` как ключ дедупа).
- `UrlScoring`:
  - скоринг следующей ссылки по эвристикам (domain trust/путь/якорь/контекст/глубина);
  - penalize повторов/параметров/“тонких” страниц.
- Domain fairness / quotas (минимально):
  - ограничить число задач на домен в окне, чтобы не “залипать” на одном сайте.

### Критерии готовности

- Frontier принимает “discovered_urls” и выдаёт следующий `CrawlTask` в предсказуемом порядке при одинаковом входе.
- Дедуп по `url_norm` гарантирует отсутствие повторных задач на одну и ту же нормализованную ссылку в рамках `run_id`.

### Тесты

- Unit: нормализация URL, дедуп, порядок pop при одинаковых данных.
- Unit: url scoring — золотые кейсы (кандидаты → сортировка).

---

## 6) Блок D — RelevanceGate.score() (скоринг контента)

**Ссылка на справочник:** `§19.1 шаг 7`, `§22.7`, `§25.2 (novelty/marginal gain)`  
**Приоритет:** P0 (контроль стоимости, качество выдачи, stop-signals)

### Что добавляем/меняем

- Ввести `RelevanceGate` с контрактом:
  - вход: нормализованный `PageArtifact` (уже после extraction),
  - выход: решение `index | skip | defer` + причины/метрики.
- Минимальные метрики качества:
  - `content_score`,
  - `boilerplate_ratio`,
  - `is_relevant`,
  - `content_hash` для дедупа по контенту.
- Novelty tracking (минимально):
  - “новизна” как доля новых `content_hash` и новых доменов/URL в окне N.

### Критерии готовности

- Gate стабильно отклоняет очевидный шум (nav-only/404/empty) и пропускает контентные страницы.
- Решение gate записывается в `events.ndjson` и влияет на ingestion (index только при `index`).

### Тесты

- Unit: эвристики gate на наборе “шум/контент”.
- Integration: crawl нескольких страниц → gate decisions отражаются в stats.

---

## 7) Блок E — StopPolicy (hard + soft stop)

**Ссылка на справочник:** `§25`  
**Приоритет:** P0 (без этого deep search неуправляем)

### Что добавляем/меняем

- Контракт `StopSignals` и `StopPolicy.should_stop()`.
- Hard stop:
  - `max_depth`, `max_pages`, `max_runtime_sec`,
  - `resource_limit_hit` (длительное превышение),
  - `budget_exhausted` (embedding/LLM budget).
- Soft stop (минимальный набор):
  - `marginal_gain` по окну (сколько “index”-решений за N),
  - `novelty_ratio` по окну,
  - `domain_saturation` (много дубликатов по `content_hash`).

### Критерии готовности

- Run завершает deep search не только по max_pages, но и по “полезность упала” при стабильных сигналах.
- Причина stop фиксируется в `RunResult`/manifest.

### Тесты

- Unit: политики stop на синтетических временных рядах сигналов.

---

## 8) Блок F — ExtractionPipeline + LinkDiscovery + DiffEngine

**Ссылка на справочник:** `§8`, `§20`, `§22.5`, `§22.6`  
**Приоритет:** P1 (нужно и crawler, и agent loop, и dedup)

### Что добавляем/меняем

- `ExtractionPipeline.extract()` как отдельный слой:
  - input classifier (html/pdf/binary),
  - HTML clean (boilerplate removal),
  - link extraction + normalization (internal/external + discovered_urls),
  - markdown renderer,
  - snapshot builder (нормализованная модель),
  - `content_hash`.
- `DiffEngine`:
  - diff по нормализованным snapshots (ADD/REMOVE/UPDATE_TEXT/UPDATE_ATTR),
  - сохранить как артефакт, ссылку писать в `PageArtifact`.

### Критерии готовности

- Для одного HTML входа pipeline выдаёт одинаковый `markdown`, `links`, `content_hash`.
- Diff между двумя снапшотами не зависит от “шумных” атрибутов.

### Тесты

- Unit: html clean + link normalization + snapshot/diff.
- Golden: два фикстурных HTML → ожидаемые links/markdown/diff ops.

---

## 9) Блок G — Crawler loop + Scheduler + resource-aware concurrency

**Ссылка на справочник:** `§7.3–7.4`, `§19`, `§22.2`, `§23.3`  
**Приоритет:** P1

### Что добавляем/меняем

- Crawler tick:
  - `frontier.pop` → acquire → fetch (или lite policy) → extract → relevance → push links → persist artifacts/events.
- `ResourceController`:
  - effective concurrency step up/down по CPU/RAM,
  - “memory pressure: drain only”.
- Per-domain rate limiting (white-tier минимально).

### Критерии готовности

- Под нагрузкой concurrency адаптируется и не вылетает за hard лимит долго.
- Throughput не рушится при кратковременном pressure.

### Тесты

- Integration: небольшой run по домену (N страниц) с записью run artifacts.

---

## 10) Блок H — RAGSink (ingestion контракт) и связка с crawler

**Ссылка на справочник:** `§9`, `§21`, `§22.8`  
**Приоритет:** P1

### Что добавляем/меняем

- Ввести контракт `RAGSink.upsert_document(PageArtifact, embed_model=...)`.
- Интеграция в crawler loop:
  - ingestion вызывается только после `RelevanceGate == index`,
  - ошибки ingestion → deferred (очередь/маркер) без потери артефактов.

### Критерии готовности

- Crawler run возвращает `rag_document_ids` и пишет их в manifest.
- Upsert идемпотентен по `content_hash + chunk_offset` (на уровне sink).

### Тесты

- Integration: upsert в Postgres на тестовом стенде (если уже есть инфраструктура).

---

## 11) Блок I — AntiBotPolicyEngine (signals → plan) + plugin chain

**Ссылка на справочник:** `§6`, `§23.9`  
**Приоритет:** P2

### Что добавляем/меняем

- `AntiBotPolicyEngine`:
  - вход: status/redirect patterns/js markers/latency spikes,
  - выход: mitigation plan (rotate proxy, retry, degrade mode).
- Plugin chain:
  - detect/mitigate контракты.

### Критерии готовности

- На доменах со 403/429 число успешных fetch увеличивается без бесконечных retry.

---

## 12) Блок J — Agent loop (snapshot/diff-first) + pause/resume + human channel

**Ссылка на справочник:** `§18`, `§31`, `§33`  
**Приоритет:** P2

### Что добавляем/меняем

- `AgentStepInput/Action/Output` и loop `plan → exec → observe → diff → compress`.
- `HumanLoopBridge` контракт (note/action_required/action_done) и фиксация авторства шага в trace.
- Pause/resume:
  - save_state + pause_token,
  - restore + sanity checks + diff “pre-pause vs post-resume”.

### Критерии готовности

- Длинный агентный сценарий может быть приостановлен и продолжен без потери состояния.

---

## 13) Порядок внедрения (рекомендуемый)

1) **A (restore-mode)** + **B (run artifacts)**  
2) **C (Frontier+UrlScoring)** + **D (RelevanceGate)** + **E (StopPolicy)**  
3) **F (Extraction+Diff)**  
4) **G (Crawler loop + resource controller)**  
5) **H (RAGSink integration)**  
6) **I (AntiBot engine)** + **J (Agent loop + human channel)**

## 14) Общий Definition of Done

- Deep search определяется как связка: `Frontier + UrlScoring + RelevanceGate + StopPolicy + ExtractionPipeline`.
- Каждый run имеет `manifest.json` и `events.ndjson`, а страницы имеют артефакты по канону.
- Restore-mode работает через `restore_state_key` и даёт продолжать run без удержания warm-контекста.
