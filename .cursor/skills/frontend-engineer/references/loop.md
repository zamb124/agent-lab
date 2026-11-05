# Рекурсивный цикл режима audit

Исполняемый цикл, а не напоминание: он работает, пока discovery находит нарушения. Эталон — `target-architecture.md`; классы и детекторы — `../anti-patterns.md`; сквозные срезы-корни — `playbooks.md`; скелет цикла и приоритеты — `../SKILL.md` § Режим audit.

## Preflight

```bash
git status --porcelain > /tmp/ui_preflight_status.txt
uv run python .cursor/skills/frontend-engineer/scripts/ui_audit.py --json /tmp/ui_audit_before.json
uv run python .cursor/skills/refactor-engineer/scripts/gates_report.py /tmp/ui_gates_before
uv run python -m scripts.gates.repo.rules_drift
```

- Файлы из `/tmp/ui_preflight_status.txt` — чужие правки: не трогаются, не откатываются, не форматируются, не коммитятся.
- `gates_report.py` — все шаги `make lint` без остановки на первом падении (5–10 минут из-за basedpyright); красный шаг до среза — baseline, а не повод его скрыть.
- `ui_audit.py` — около минуты: tsc, конвейер, сигнатуры `scripts/gates/frontend/ui_canon_rules.py`, скрытые исключениями находки, слепые ссылки, мосты, нормы без гейта.

## Чтение `ui_audit.py`

| Секция | Находка означает | Приоритет |
|---|---|---|
| tsc | ошибка компиляции | P0 |
| Конвейер | звено toolchain вне эталона (`target-architecture.md` § Toolchain) | P0 |
| Сигнатуры `hard` | рост — красный `scripts/gates/frontend/ui_kit_canon.py`; остаток — хвост слоя | рост P0, остаток P4 (`ui_js_files` в `tests/` — P5) |
| Сигнатуры `soft` `ts_*` | остаток типов и замалчивания без ratchet | перевод в ratchet — P0; находки — P1 (`ts_silent_catch`, `ts_console`, `ts_literal_fallback`), P2 (`ts_explicit_any`, `ts_type_assertion`, `ts_double_cast`, `ts_non_null_assertion`) |
| Сигнатуры `soft` прочие | визуал и мелкие отступления канона | P6 |
| Скрытое | exemption или pragma прячет находку | P0 |
| Слепота | гейт, конфиг, правило или скил ссылается на `.js`, которого нет; набор суффиксов без `.ts` | P0 |
| Мосты | второй резолвер, прослойка-заглушка, import map, vendored npm; мост внутри гейта | P3; в гейте — P0 |
| Без гейта | норма без детектора | P6; норма о замалчивании или типах — P1 |

Находка — кандидат, а не приговор: открыть код, вызывающих (граф `codebase-memory-mcp`: `search_graph` → `trace_path`; без MCP — `rg`), правило-владельца. В zsh переменная со списком путей не разбивается на слова: пути — явными аргументами или через `bash -c`.

### Классы без детектора

Классы `../anti-patterns.md` с пометкой «нет» ищутся `rg`; найденный класс получает детектор первым шагом своего среза.

```bash
rg -n "this\.use(Resource|Op|Form|CursorList|Facets|Slice)\([^)]*\)\s+as\s" apps core -g '*.ts'          # каст контроллера
rg -n "^(export )?(interface|type) [A-Z]" apps/*/ui/pages apps/*/ui/modals apps/*/ui/components -g '*.ts'  # переобъявленные формы
rg -n --pcre2 "^import (?!type)[^;]*events/resources/" apps/*/ui/pages apps/*/ui/modals apps/*/ui/components -g '*.ts'  # runtime-импорт фабрики
rg -n "function \w*(Or|OrDefault|Fallback)\(" apps core -g '*.ts'                                        # хелперы-фолбеки
rg -n "dispatch\(\s*'[a-z_]+/[a-z_]+/[a-z_]+'" core/frontend/static/lib -g '*.ts'                         # литеральный тип вне CoreEvents
rg -n "\[(key|action|methodName): string\]: unknown" core/frontend/static/lib -g '*.ts'                   # индекс-сигнатура вместо типа
```

## Классификация находки

| Случай | Действие |
|---|---|
| в kit есть замена | заменить, локальную реализацию удалить в том же срезе |
| в kit замены нет | срез корня в core: компонент, тип, возможность контроллера; `kit_gap` — только при ограниченной пользователем границе |
| ложное срабатывание | исправить сигнатуру детектора; exemption, pragma и allowlist ради тишины запрещены |
| новый класс | запись в `../anti-patterns.md` + детектор |
| правило расходится с кодом | режим `rules`: правило as-is; правка правила, узаконивающая нарушение, запрещена |

## Детектор

- Сигнатура по содержимому файла — правило `scripts/gates/frontend/ui_canon_rules.py`: `soft` — только отчёт `scripts/tools/report_ui_kostyli.py`; `hard` — ratchet `scripts/gates/frontend/ui_kit_canon.py` с baseline `scripts/gates/frontend/ui_canon_baseline.json`.
- Структурная норма — гейт-владелец: `scripts/gates/frontend/ui_canon.sh`, `scripts/gates/frontend/core_frontend_canon.py`, `scripts/gates/frontend/ui_factories.py`, `scripts/gates/backend/command_rest_mirror.py`, `scripts/gates/frontend/field_canon.sh`, `scripts/gates/backend/platform_events.py`.
- Детектор падает на текущем нарушении в границе — иначе он ничего не ловит; пустой набор сканируемых файлов и отсутствующий ожидаемый файл — падение, а не «OK».
- Остаток больше одного среза — hard-правило с текущим числом; срез снижает число, `--update` фиксирует только снижение.
- В правиле-владельце снять `[без гейта]` и вписать гейт в раздел «Гейты».

## Правка и рекурсия

- Playbook корня — `playbooks.md`; правка файла — `../recipes.md`.
- Рекурсия — `../SKILL.md` § Рекурсия; стек срезов записывается в отчёт: «A → корень B (закрыт) → A (закрыт)».
- Серия большого корня: каждый шаг — зелёный `make ui` и ratchet не выше; между шагами нет runtime-адаптеров, дублирующих API и параллельных веток кода.

## Проверка

1. Детектор среза — 0 в границе; повторный `ui_audit.py` не находит заменённого имени, пути, моста или исключения.
2. `make ui`; затронуты Python, гейты или правила — `make lint` или `gates_report.py` без новых падений относительно preflight.
3. Ratchet снизился — `uv run python -m scripts.gates.frontend.ui_kit_canon --update`.
4. Затронут экран — визуальная проверка (`../SKILL.md` § Визуальная проверка).
5. Красное из-за среза чинится до зелёного; красное не из-за среза показывается отдельно с доказательством из preflight.

## Отчёт итерации

По-русски, кратко, результат до процесса:

- срез, корень, инвариант, эталон и норма-владелец; стек рекурсии, если был;
- детектор: был или добавлен; N → 0;
- убрано: заменённые пути, мосты, исключения, мёртвые артефакты;
- гейты до и после, тесты, ratchet до → после, дельта `ui_audit.py` по секциям;
- **Найдено и не исправлено** — каждая открытая находка с приоритетом и предлагаемым срезом; пустой раздел — «нет»;
- следующий срез из свежего discovery.

## Стоп-условия

UI соответствует эталону, только когда одновременно: `tsc` — 0; все пункты § Конвейер — OK; сигнатуры hard и soft — 0 (кроме принципиальных исключений, оформленных `Исключение:` в правиле-владельце); § Скрытое, § Слепота, § Мосты пусты; нормы `[без гейта]` в UI-правилах закрыты детекторами; `make ui` и `make lint` зелёные. До этого каждый запуск заканчивается следующим срезом, а не итоговым «готово».
