---
name: refactor-engineer
description: "Автономный рефакторинг Платформы под канон .cursor/rules: находит нарушения (логика в op_*, SQL в сервисах, таблицы вне models/<entity>.py, DI, транспорт команд, мапперы и twin-модели, широкие типы, копипаста между сервисами, layout, дрейф правил), при отсутствии детектора сначала добавляет гейт и закрывает один сквозной срез до зелёного make lint и тестов домена. Использовать при запуске без аргументов, при просьбах «выровняй под архитектуру», «приведи в соответствие с правилами», «стандартизируй сервис», при ошибках basedpyright и ratchet-долге, контрактах методов моделей Oxyde и расхождении правил с кодом."
---

# Refactor Engineer

Один запуск — один логический срез: найти нарушение канона, при отсутствии детектора добавить его, протянуть исправление через весь call stack и доказать гейтами и тестами. Канон — `.cursor/rules/`: `main.mdc`, `architecture.mdc`, `rules.mdc` и правило-владелец домена. Этот скил — только процедура; норму он не формулирует и не пересказывает.

## Режимы

| Режим | Когда | Результат |
|---|---|---|
| `slice` (по умолчанию) | запуск без уточнений, «выровняй X» | один закрытый срез нарушений кода |
| `types` | basedpyright, ratchet `cast_calls`/`object_annotations`/`type_ignore` | источник потери типа вылечен, счётчик ниже |
| `models` | контракты методов `PlatformModel` | одно семейство имён приведено к `database.mdc` § Имена методов |
| `rules` | правило расходится с кодом или с `rules.mdc` | правило исправлено as-is |
| `gate` | норма с меткой `[без гейта]` | детектор добавлен, метка снята |

Пользователь назвал домен, сервис, файл или класс нарушения — это граница discovery. Иначе срез выбирается по приоритетам ниже.

## Цикл

### 1. Preflight

- `git status --porcelain > /tmp/refactor_preflight_status.txt` — чужие незакоммиченные правки не трогаются, не откатываются и не форматируются. `git stash`, `git reset`, `git checkout -- <file>` запрещены.
- Прочитать `main.mdc`, `architecture.mdc`, `rules.mdc`. Правило-владелец домена читается целиком после выбора среза.
- Baseline гейтов: `uv run python .cursor/skills/refactor-engineer/scripts/gates_report.py /tmp/refactor_gates_before` — все шаги `make lint` без остановки на первом падении.

### 2. Discovery

Команды — `references/discovery.md`, классы нарушений и их детекторы — `references/violation-catalog.md`.

- Гейты в режиме отчёта (baseline выше) и ratchet по файлам: `uv run python .cursor/skills/refactor-engineer/scripts/ratchet_list.py [<metric>]`.
- Детекторы классов из каталога в границе запуска.
- Нормы без детектора: `rg -n "\[без гейта\]" .cursor/rules`.
- Дрейф правил: `uv run python -m scripts.gates.repo.rules_drift`.

Совпадение — кандидат, а не приговор: открыть код, вызывающих (граф `trace_path` или `rg`), правило-владельца. Исключение из запрета существует только как пункт `Исключение:` правила-владельца.

### 3. Выбор среза

Приоритет (первый непустой):

1. **P0 — сломанный контроль.** Гейт не падает на нарушении, регресс ratchet относительно `scripts/gates/backend/ratchet_baseline.json`, красный шаг `make lint`, дрейф правил, вводящий агента в заблуждение.
2. **P1 — безопасность и деньги.** Check и dual-write OpenFGA, billing span, изоляция `company_id`, секреты.
3. **P2 — слои.** Логика в `op_*`, `objects`/`execute_raw`/`atomic` в сервисе, бизнес в модели, таблица вне `models/<entity>.py`, `apps/<svc>/db/`.
4. **P3 — контракты.** Twin-модели, мапперы, glue, клиенты вне `core/clients/`, копипаста между сервисами, дубль `core` ↔ `apps`.
5. **P4 — строгость.** `cast`, `object`, `Any`, `HTTPException`, `getattr`-фолбек, `or`-фолбек, локальные импорты, `os.environ`.
6. **P5 — имена и layout.**

Размер: одно семейство нарушения в одной логической границе; все вызывающие входят в срез; цель — 4–12 файлов-владельцев или 6–20 методов. Больше — разделить по домену до правок; меньше — закрыть семейство целиком, не добавляя несвязанное. В одном срезе не смешиваются: перенос слоя и переименование; hard delete и soft delete; PK upsert и append/version; tenant-scope и naming; разные классы из каталога.

### 4. Контракт среза

До первой правки записать и показать пользователю:

```text
Срез: <класс нарушения> в <граница>.
Норма: <file>.mdc § <Раздел>.
Инвариант: <одна проверяемая фраза>.
Детектор: <гейт или команда>; сейчас находит N.
```

### 5. Сначала детектор

- Гейт есть — запустить, зафиксировать N.
- Гейта нет — добавить проверку в существующий скрипт `scripts/` того же канона; новый скрипт — только если подходящего нет, тогда он регистрируется в `mk/lint.mk` (`_lint-py`) или в `check-events-canon` (`Makefile`). Детектор обязан упасть на текущем коде в границе среза — иначе он ничего не ловит.
- Долг больше одного среза — ratchet-метрика в `scripts/gates/backend/ratchet_counts.py` (`METRICS`) с текущим числом в `scripts/gates/backend/ratchet_baseline.json`; срез снижает число.
- Allowlist — только принципиальные исключения, каждое оформлено `Исключение:` в правиле-владельце.
- В правиле-владельце снять метку `[без гейта]` и вписать гейт в раздел «Гейты».

Порядок действий — `references/playbooks.md` § Добавить детектор.

### 6. Сквозная правка

- Playbook класса — `references/playbooks.md`.
- Место кода — по тесту `main.mdc` § Куда писать код.
- Контракт меняется целиком: сигнатура, payload, response, события, UI-фабрики, тесты, фикстуры, документация.
- Старый путь удаляется: wrapper, alias, re-export, compat, deprecated-метод не остаются.
- Новый код — только в каноническом месте: `models/<entity>.py`, `services/`, `realtime/`, `api/`, `core/clients/`, `core/<domain>/`.

### 7. Проверка

- Детектор среза: 0 в границе. Повторный discovery границы не находит старое имя или путь.
- `uv run python .cursor/skills/refactor-engineer/scripts/gates_report.py /tmp/refactor_gates_after` — новых падений относительно baseline нет; `make lint` зелёный, если baseline был зелёным.
- Ratchet снизился — `uv run python -m scripts.gates.backend.ratchet_counts --update` (только вниз).
- Тесты: `make test-up` один раз, затем `uv run pytest tests/<домен>/ -q` и архитектурные тесты (`tests/core/di/test_service_kit.py`, `tests/core/realtime/test_command_owners.py`, `tests/realtime/test_<svc>_commands.py`); UI — `make ui`.
- Красное из-за среза чинится до зелёного. Красное не из-за среза показывается отдельно с доказательством из baseline.

### 8. Правило-владелец

Факты, изменённые срезом (пути, символы, гейты, метки), обновляются в правиле-владельце as-is в том же изменении по `rules.mdc`. Правка правила, узаконивающая нарушение, запрещена — это блокер `rule_change_required`.

### 9. Отчёт

По-русски, кратко:

- срез, инвариант, норма-владелец;
- детектор: был или добавлен; находил N → 0;
- что перенесено и удалено (старые пути и имена);
- проверки: шаги lint до/после, тесты; pre-existing падения отдельно;
- ratchet до → после;
- следующий срез из свежего discovery.

Платформа не объявляется выровненной, пока discovery находит нарушения. Следующий запуск снова начинает с preflight и discovery.

## Блокеры

Остановиться без костыля; дать доказательство и одно рекомендуемое решение:

- `rule_conflict` — обязательные нормы требуют несовместимого, приоритет `main.mdc` конфликт не решает;
- `rule_change_required` — корректное решение вводит новый общий канон;
- `ambiguous_owner` — нельзя определить модель-владельца данных или сервис-владельца сценария;
- `composite_key_mismatch` — фактический ключ таблицы не совпадает с Oxyde PK;
- `external_contract` — имя или форма зафиксированы внешней спекой;
- `blast_radius_not_cohesive` — срез нельзя отделить от независимых доменов;
- `infra_unavailable` — тестовый стек не поднимается; срез не объявляется завершённым.

## Запреты процесса

- `cast`, `# type: ignore`, `Any`, `object`, `getattr(..., default)`, `or`-фолбек, локальный импорт, wrapper, alias, shim, compat-слой ради зелёного прогона.
- Ослабление гейта, расширение allowlist ради прохождения, `--update` ratchet вверх, `pytest.skip`, `AsyncMock`, `monkeypatch` внутренних компонентов.
- Правки вне границы среза, попутный cleanup несвязанного кода, форматирование чужих файлов.
- Новый канон без правки правила-владельца.

## References

- `.cursor/skills/refactor-engineer/references/discovery.md` — команды discovery и baseline.
- `.cursor/skills/refactor-engineer/references/violation-catalog.md` — класс → норма → детектор → целевая форма.
- `.cursor/skills/refactor-engineer/references/gates.md` — гейты: запуск, вывод, allowlist.
- `.cursor/skills/refactor-engineer/references/playbooks.md` — рецепты срезов и добавления детектора.
- `.cursor/skills/refactor-engineer/scripts/gates_report.py` — все шаги `make lint` в режиме отчёта.
- `.cursor/skills/refactor-engineer/scripts/ratchet_list.py` — нарушения ratchet по файлам.
- `scripts/gates/repo/rules_drift.py` — дрейф `.cursor/rules` относительно кода и `rules.mdc`.
