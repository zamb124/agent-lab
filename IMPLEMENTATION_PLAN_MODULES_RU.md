# План реализации по модулям (исполнение)

Документ описывает **пошаговую реализацию** целевой архитектуры по модулям и зависимостям.  
`TARGET_ARCHITECTURE_RU.md` остается **справочником/контрактом архитектуры**; этот файл — рабочий план внедрения.

## 1) Правило связи со справочником

Для каждого модуля здесь указывается:
- `Ссылка на справочник`: разделы в `TARGET_ARCHITECTURE_RU.md`, которые задают контракт;
- `Результат`: что должно быть готово в коде;
- `Критерии готовности`: проверяемые условия;
- `Тесты`: минимальный набор.

Формат ссылок: `TARGET_ARCHITECTURE_RU.md §<номер раздела>`.

---

## 2) Этапы внедрения (макропорядок)

1. **Браузерное ядро v1: Playwright + Lightpanda**  
   Основа для всего остального: lifecycle, CDP-подключение, сессии, acquire/fetch/release.
2. **Browser Control API + адаптеры совместимости**  
   Единый интерфейс поверх Playwright/browser-use/agent-browser.
3. **Visibility Tree + snapshot/diff-first контекст для LLM**  
   Экономия токенов и стабильный state loop.
4. **Control Plane + Scheduler + ResourceController**  
   Запуски, лимиты RAM/CPU, динамический concurrency.
5. **Discovery/Frontier/Deep Crawl**  
   Поиск и управление обходом графа URL.
6. **Extraction/Normalization pipeline**  
   Очистка HTML, markdown, ссылки, профили output.
7. **RAG ingestion + rerank**  
   Chunk -> bge-m3 -> pgvector + каскад ранжирования.
8. **Agent Runtime loop + human-in-the-loop**  
   План/выполнение/наблюдение/сжатие + pause/resume.
9. **Anti-bot engine + plugin chain**  
   Детект, mitigation, tier policy.
10. **Artifacts/Observability/CDP tooling**  
    Трассировка, артефакты, replay, инспекция.

---

## 3) Модуль 01 — Browser Runtime v1 (Playwright + Lightpanda)

**Ссылка на справочник:** `§5`, `§17`, `§30`, `§31`  
**Приоритет:** P0  
**Цель:** поднять минимально жизнеспособное браузерное ядро для crawler/agent.

### Что реализуем

- `CDPConnectionPool` для endpoint-ов Lightpanda/Chromium.
- `ContextFactory` с сигнатурой контекста (proxy/storage/stealth/profile/mode).
- `PageLeaseManager`:
  - `acquire(page_mode)` / `release(page)`,
  - refcount, TTL, lock от гонок.
- `SessionStateStore`:
  - save/restore cookies + localStorage/sessionStorage + last snapshot ref.
- `BrowserInteractor` (базовый контракт):
  - `acquire`, `fetch`, `exec_code`, `save_state`, `restore_state`, `release`.

### Минимальные API-результаты

- Рабочий путь `acquire -> fetch -> release` для одного URL.
- Поддержка `wait_policy` (`domcontentloaded`, `networkidle`, `selector:*`).
- Поддержка `warm` и `restore` режимов.
- Нормализованный результат fetch (`final_url`, `status_code`, `headers`, refs артефактов).

### Критерии готовности

- 100 последовательных acquire/release без утечек page/context.
- Успешный restore сессии после полного закрытия контекста.
- Явный graceful drain и kill_session для зависших сессий.

### Тесты

- Unit: сигнатура контекста, refcount, ttl-expire, lock behavior.
- Integration: real Playwright + Lightpanda endpoint, save/restore state.
- Soak: циклический acquire/fetch/release под параллелизмом.

---

## 4) Модуль 02 — Browser Control API и обратная совместимость

**Ссылка на справочник:** `§17.3`, `§30`, `§34`  
**Приоритет:** P0  
**Цель:** единый управляющий интерфейс, независимый от конкретного backend.

### Что реализуем

- `BrowserControlAdapter` + `BrowserControlFeatures`.
- Адаптеры:
  - `PlaywrightAdapter` (основной путь),
  - `BrowserUseAdapter` (совместимость с `browser_use/dom/service.py`, `browser_use/dom/serializer/serializer.py`, legacy `browser_use/dom/buildDomTree.js`),
  - `AgentBrowserAdapter` (совместимость с `agentic-browser`: `src/session/browser-controller.ts`, `src/session/session-manager.ts`, `src/transport/control-api.ts`).
- `AdapterFactory` по конфигу.

### Критерии готовности

- Один и тот же orchestration-код работает с разными адаптерами без изменений.
- `features()` корректно отражает capability backend-а.
- Неподдерживаемая capability отрабатывает предсказуемо (typed error), без падения процесса.

### Тесты

- Contract tests для всех адаптеров.
- Golden tests одинакового результата для `navigate/get_content/get_visibility_tree`.

---

## 5) Модуль 03 — Visibility Tree и token-efficient контекст

**Ссылка на справочник:** `§20.4`, `§18`, `§20`  
**Приоритет:** P0  
**Цель:** сократить токены и улучшить действие LLM через видимое интерактивное дерево.

### Что реализуем

- Построитель `visibility_tree` (JS injection + CDP-помощники):
  1. visibility filter;
  2. interactivity filter;
  3. semantic filter.
- Отдельный канал `accessibility_tree` как дополнительный слой.
- `selector_map` для стабильных действий/реплея.
- `LLMContextCompressor` с budget-профилями (`tiny`, `balanced`, `quality`).

### Почему не только Playwright accessibility snapshot

- Недостаточная видимость JS-listeners без CDP;
- избыточность AX-узлов для next-action;
- слабая связка с replay/selectors;
- менее устойчивый step-diff для loop.

### Критерии готовности

- Сокращение контекста минимум на 40% токенов против raw snapshot.
- Не хуже baseline по success-rate на эталонных агентных сценариях.
- Стабильный `selector_map` между соседними шагами.

### Тесты

- Unit: фильтры visibility/interactivity/semantic.
- Integration: DOM+AX+CDP listeners корреляция.
- Eval: A/B по качеству действий агента и стоимости токенов.

---

## 6) Модуль 04 — Control Plane, run state machine, API запусков

**Ссылка на справочник:** `§2`, `§4`, `§11`, `§22`, `§23.5`  
**Приоритет:** P1

### Что реализуем

- `RunController` и state machine (`CREATED -> RUNNING -> DRAINING -> DONE/FAILED`).
- API:
  - create/start run,
  - get status/progress,
  - stop/drain/terminate.
- Валидация `RunRequest`.
- Единый `RunResult`.

### Критерии готовности

- Идемпотентный start/stop.
- Воспроизводимый статус run при рестарте control-plane.

---

## 7) Модуль 05 — Scheduler и ResourceController

**Ссылка на справочник:** `§7`, `§19`, `§22.2`  
**Приоритет:** P1

### Что реализуем

- Диспетчер задач из frontier.
- Dynamic concurrency controller:
  - step up/down по RAM/CPU,
  - memory pressure режим drain.
- Квоты домена/рантайма/бюджета.

### Критерии готовности

- Нет перегрева RAM/CPU выше hard-limit дольше допустимого окна.
- Throughput не деградирует на стандартных доменах при адаптации.

---

## 8) Модуль 06 — Discovery, SearchProviders, Frontier, Crawl стратегии

**Ссылка на справочник:** `§7`, `§19`, `§25`  
**Приоритет:** P1

### Что реализуем

- `SearchProviderManager` (старт с DuckDuckGo, расширяемый интерфейс).
- `FrontierManager`:
  - priority queue,
  - visited/dedup,
  - depth/domain policies.
- Стратегии обхода: BFS/DFS/hybrid.
- Stop policy: hard + soft сигналы.

### Критерии готовности

- Строгая дедупликация нормализованных URL.
- Стабильное завершение deep search по stop policy.

---

## 9) Модуль 07 — Extraction/Normalization

**Ссылка на справочник:** `§8`, `§20`, `§21`  
**Приоритет:** P1

### Что реализуем

- Pipeline:
  - input classifier,
  - clean html,
  - link extraction,
  - markdown/snapshot/diff output.
- Профили:
  - `rag_profile`,
  - `agent_profile`.
- Lite-path для HTML/PDF без тяжелого рендера.

### Критерии готовности

- Повторяемая нормализация (стабильный output при одинаковом input).
- Валидный markdown и snapshot для всех целевых типов страниц.

---

## 10) Модуль 08 — RAG ingestion + reranking

**Ссылка на справочник:** `§9`, `§24`, `§26`, `§29`  
**Приоритет:** P1

### Что реализуем

- Chunker + embedder (`bge-m3`) + upsert в Postgres vector store.
- Многоступенчатый rerank (`fast`, `balanced`, `quality`).
- Evidence pack для финального QA loop.

### Критерии готовности

- Идемпотентный upsert по `content_hash + chunk_offset`.
- Измеримый прирост quality метрик после rerank.

---

## 11) Модуль 09 — Agent Runtime loop + human-in-the-loop

**Ссылка на справочник:** `§18`, `§31`, `§33`  
**Приоритет:** P1

### Что реализуем

- Цикл `plan -> execute -> observe -> compress -> decide`.
- Пауза/возобновление:
  - `PAUSED`, `RESUMING`, TTL политики.
- Human messages (`note`, `action_required`, `action_done`).
- Отдельное логирование авторства шага (`agent` vs `human`).

### Критерии готовности

- Resume после паузы без потери контекста шага.
- Корректное переключение на ручное вмешательство и обратно.

---

## 12) Модуль 10 — Anti-bot engine

**Ссылка на справочник:** `§6`, `§23.9`  
**Приоритет:** P2

### Что реализуем

- `AntiBotPolicyEngine`.
- Плагины detect/mitigate.
- White/aggressive tiers и escalation logic.

### Критерии готовности

- Видимый прирост success-rate на “сложных” доменах.
- Нет бесконечных retry-loop.

---

## 13) Модуль 11 — Artifacts, Observability, CDP tools

**Ссылка на справочник:** `§10`, `§32`, `§34`, `§35`  
**Приоритет:** P2

### Что реализуем

- `ArtifactWriter`:
  - `manifest.json`,
  - `events.ndjson`,
  - page artifacts,
  - browser trace timeline.
- `CDPRegistry`, `CDPInspector`, `CDPRecorder`, `CDPReplayHelper`.
- Метрики latency/retry/blocked/token-usage.

### Критерии готовности

- Полный replay run по артефактам.
- Возможность форензики без повторного запуска.

---

## 14) Сквозные зависимости между модулями

- Модуль 01 обязателен перед 02, 03, 09.
- Модуль 02 обязателен перед 04/05/09 (единый интерфейс).
- Модуль 03 обязателен перед production-версией 09 (token budget loop).
- Модуль 04 обязателен перед 05 и 06 (оркестрация run).
- Модуль 06 и 07 обязаны завершиться до полного 08.
- Модуль 11 подключается инкрементально с первых этапов, но “полный forensic” — после 09/10.

---

## 15) План релизных волн

### Волна A (MVP runtime)
- Модуль 01 + базовый 04 + базовый 11.
- Демо: один run, один URL, артефакты, restore сессии.

### Волна B (совместимость и контекст)
- Модуль 02 + 03.
- Демо: один сценарий агента с переключением адаптеров без изменения orchestration-кода.

### Волна C (краулер ядро)
- Модуль 05 + 06 + 07.
- Демо: deep crawl по домену с динамическим concurrency и stop policy.

### Волна D (RAG и качество ответа)
- Модуль 08 + 09.
- Демо: deep search -> rerank -> grounded answer с citations.

### Волна E (устойчивость production)
- Модуль 10 + расширенный 11.
- Демо: антибот-эскалация + полный replay/forensic проблемного run.

---

## 16) Definition of Done для всей инициативы

- Любой этап pipeline трассируем в `events.ndjson` и browser trace.
- LLM контекст формируется snapshot/diff/visibility-tree-first, а не raw HTML-first.
- Один orchestration-код работает с разными browser backend через adapter interface.
- Есть воспроизводимый E2E сценарий: `query -> deep search -> rerank -> answer + citations`.
- Run можно безопасно остановить, возобновить или восстановить после паузы.
