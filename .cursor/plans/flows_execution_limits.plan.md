# Лимиты выполнения Flows (обновлённый план)

## Решения по дизайну (зафиксировано)

### A. Wall-clock: весь flow — **вариант B (deadline в state)**

- В **`ExecutionState`** хранить дедлайн (предпочтительно **monotonic** время + `time.monotonic()`, а не только `time.time()` — меньше сюрпризов при NTP; либо пара: `flow_run_started_at_monotonic` + `flow_timeout_seconds` с вычислением дедлайна).
- Проверки:
  - в начале каждой итерации основного цикла в [`flow.py`](apps/flows/src/runtime/flow.py) (`_execute_loop`);
  - внутри существующего пути **отмены** — унифицировать с [`check_cancellation`](apps/flows/src/state/cancellation.py) (один тип ошибки/статуса: «превышен лимит времени flow»), чтобы вложенные flow и long-running пути тоже видели дедлайн.
- **`FlowConfig.timeout`**: ввести/подтвердить семантику **секунды wall-clock на run**; дефолт с сервера + **жёсткий потолок 3600 с (1 час)** на уровне валидации Pydantic и/или настроек сервиса (zero-guess: явный cap в `FlowSettings` или константа).

**Почему B надёжнее, чем только `asyncio.wait_for` вокруг `run`:** дедлайн проверяется **внутри** цикла — корректнее обрывают вложенные вызовы и единообразна отмена; `wait_for` снаружи остаётся опциональным safety-net на границе TaskIQ/HTTP, но не единственным механизмом.

### B. Wall-clock: **каждая нода (универсально)**

- В **`NodeConfig`** (или согласованное имя, например `node_timeout_seconds`) — опциональное поле; **валидация**: положительное целое, **не больше глобального cap** (тот же разумный максимум, согласованный с flow — например 3600 с или отдельный `max_node_timeout_seconds` в settings ≤ 3600).
- Выполнение: оборачивание **`run` ноды** в `asyncio.wait_for(..., timeout=...)` **на границе единого места** (например `BaseNode._run_internal` или единая обёртка в `Flow` перед `node.run`) — одна реализация, все типы нод.

**Ограничение (не забывать):** `wait_for` **не** прерывает чисто синхронный CPU-bound бесконечный цикл в Python в том же потоке — для этого нужен либо subprocess, либо статический запрет/эвристики (см. раздел D).

### C. UI

1. **Flow (редактор flow / настройки skill или корневой конфиг):** поле «таймаут выполнения flow (с)» с **slider/stepper** или числовым вводом, **min** ≥ 1, **max ≤ 3600** (1 час) — product: не больше часа.
2. **Каждая нода, без исключения:** в общем слое — [`flows-base-node-editor.js`](apps/flows/ui/components/nodes/flows-base-node-editor.js) (или один общий встраиваемый блок настроек) — поле **«лимит времени ноды (с)»** с тем же **глобальным max** в UI; type-specific редакторы **не** дублируют логику, только наследуют базовую секцию.
3. i18n: `core/i18n/translations/{ru,en}/flows.json` — новые ключи парно.
4. Канон UI: настройки через **фабрику** и существующие патчи `nodeConfig` (см. [`frontend.mdc`](.cursor/rules/frontend.mdc)) — не ad-hoc fetch в компонентах.

### D. Синхронные бесконечные циклы в `code_node` — статическая проверка

**Вопрос:** «Можем ли проверять код на наличие синхронных операций и не запускать?»

- **Полный запрет «синхронных операций»** (любой sync-код) — **нецелесообразен**: обычный `def execute` и вызовы в namespace синхронны по умолчанию; это нормальный режим.
- **Полная остановка проблемы «всех» бесконечных циклов** — **невозможна** (undecidable, аналогично остановке).
- **Реалистичный путь — эвристики AST** в существующем [`_validate_code`](apps/flows/src/eval/compiler.py) / `PythonCompiler.validate` (уже есть `ast.walk`):
  - запрет **очевидных** вечных циклов на верхнем уровне: например `while True:`, `while 1:`, `while 0xFF:` (литерал truthy) — с понятной ошибкой `SafeEvalError` / отдельный подкод;
  - опционально: `for` по бесконечным итераторам-константам (сложнее, второй этап).
- **Останется зазор:** `while i < 10**9`, рекурсия без базы, тяжёлый sync-код — всё ещё возможны; их ловят **дедлайн ноды** (если await даёт event loop) или **дедлайн flow** не помогут при чистом CPU spin — снова **subprocess/изоляция** как отдельная фаза, если продукт потребует.

**Для JS/Go** (если в [`CodeNode`](apps/flows/src/runtime/nodes.py) вне Python): аналогичные локальные правила/линтер в соответствующем runner, единая политика «denylist паттернов».

---

## Исследование: что уже есть (кратко)

| Механизм | Где | Заметка |
|----------|-----|---------|
| Итерации графа | `MAX_ITERATIONS = 100` в `flow.py` | Не секунды |
| Повторы `code` | `MAX_FUNCTION_CALLS = 5` | Только `code` |
| ReAct | `react.max_iterations` в `llm_runner` / `NodeConfig` | Внутри `llm_node` |
| `FlowConfig.timeout` в модели | `flow_config.py` | **Не** проверялось в run-пути channel |
| Память user code | — | Процесс, без cap |

---

## Порядок реализации (после подтверждения)

1. **Модель + state:** поля дедлайна flow в `ExecutionState`; поле таймаута ноды в `NodeConfig` + Pydantic caps; при необходимости миграция/версия конфига flow в БД.
2. **Рантайм:** инициализация дедлайна при создании/старте run; проверки в `Flow._execute_loop` + `check_cancellation`; `wait_for` на уровне ноды; новое исключение (или существующее «flow execution time») с ясным кодом для API/UI.
3. **API validate:** обновить `/flows/api/v1/code/validate` при добавлении AST-эвристик для Python.
4. **UI:** flow-level + base node editor, лимит 1 ч в слайдере/валидации на клиенте (дублирующий guard на бэке обязателен).
5. **Тесты:** unit на deadline (мок monotonic), на AST-запрет `while True`, на cap в схеме.

---

## Открытые продуктовые точки (не блокируют план)

- Отдельный cap для **node** vs **flow** (одинаковые 3600 с или node ≤ flow).
- Поведение при timeout: `exception_as_response` / статус A2A / запись в `execution_exceptions` — согласовать с [`exception_policy`](apps/flows/src/runtime/exception_policy.py).

---

## Todos (трекер)

- [ ] Утвердить имена полей: `node_timeout_seconds`, `flow_timeout_seconds` / `flow_deadline_monotonic` в state
- [ ] Реализовать state + проверки + node `wait_for`
- [ ] UI: flow editor + `flows-base-node-editor` для всех типов нод, max 3600
- [ ] AST-эвристики `while True` (и согласованные) в `PythonCompiler.validate` + тесты
- [ ] Документация внешнего разработчика при изменении `NodeConfig` / state — по правилам `main.mdc` при необходимости
