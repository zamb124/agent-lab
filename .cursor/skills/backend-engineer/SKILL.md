---
name: backend-engineer
description: Backend инженер Платформы. Использовать при правках Python в core/**, apps/**, tests/**; при DI/ContainerDep, FastAPI routes, repositories, services, TaskIQ, flows runtime, LLM config, Pydantic models, migrations, ruff, basedpyright, локальных импортах, циклических зависимостях, тестовой инфраструктуре и архитектурных рефакторах.
---

# Backend Engineer — Платформа

## База

Перед правкой читать: `main.mdc`, `architecture.mdc`, `ai_models.mdc`, `database.mdc`, `testing.mdc` и правило сервиса (`flows.mdc`, `crm.mdc`, `sync.mdc`, `rag.mdc`, `office.mdc`, `voice.mdc`).

Канон: **строгая типизация, top-level imports, DI через контейнер, один доменный контракт, реальные тесты**.

## Zero Translation / Deep Contract Refactoring

Канон — **`main.mdc`** (запреты 11–14) и **`architecture.mdc`**.

- Не создавай промежуточные mappers/adapters/`convert_*`/`*_to_*`/`*_from_*`, чтобы «не трогать» callers.
- Несовпали типы или поля — меняй контракты upstream и downstream по всей цепочке (API, service, repository, events, UI, tests).
- Минимизация blast radius заплатами и glue вокруг устаревшего интерфейса **запрещена**.
- Одна бизнес-сущность — одна модель. Twin `*DTO`/`*Internal`/`*Response` с теми же полями — дефект.
- Конвертация только на внешней границе (wire/SDK/сырой JSON→typed / ORM→domain в repository).

## Правила кода

- HTTP-слой тонкий: Pydantic payload → `container.<service>` → response. Контейнер в route только как `container: ContainerDep`.
- Бизнес-логика живёт в `services/`, доступ к данным — через repositories из контейнера. Прямые `httpx.AsyncClient` между сервисами запрещены; если REST нужен по контракту — `ServiceClient`.
- Локальные импорты в `core/` и `apps/` запрещены. Цикл чинится перестройкой слоёв: contracts/models ниже, orchestration выше, зависимости передаются через контейнер.
- Не создавать вторую Pydantic-модель с теми же полями. Если смысл один — модель одна; request/patch модели допустимы только при реально другой форме.
- `Any` только на JSON/внешней границе и сразу валидируется. Публичные методы сервисов, repositories, runtime и API имеют полные аннотации.
- `try/except` только вокруг IO/внешних сервисов; бизнес-ошибки не глушатся.

## Flows / LLM

AI-layer — только `core.ai`: provider specs, shared model catalog, resolver, runtime. Provider-specific discovery — только `core.ai.adapters`; сервисы не импортируют provider clients и не вызывают старый `get_llm(...)`.

Одна LLM-попытка — `core.ai.llm_config.LLMCallConfig`. `NodeLLMOverride` и `LLMResourceConfig` используют этот контракт; `fallback_models` — ordered `list[LLMCallConfig]`. `string[]`, урезанные fallback-модели и миграции старого формата запрещены.

## Проверки

После правок кода — **обязательно до завершения задачи**, не после ответа пользователю:

```bash
uv run ruff check <изменённые-py-файлы>   # или apps core при широких правках
uv run basedpyright --level warning --warnings apps core   # минимум; warnings = fail в test-static
make lint <path>                            # точечно: ruff + basedpyright на файл
make lint                                   # всё перед PR
make lint-ts                                # только frontend
```

После узкой правки — целевой `pytest`. После архитектурного рефакторинга — `make test`. Если менялись gate/coverage/тест-инфра или пользователь просил coverage — `make test-cov`.

**Задача не завершена**, пока: ruff зелёный; `basedpyright --level warning --warnings apps core` exit 0 (0 errors **и** 0 warnings в gate); `analyze_imports.py` → `Total local imports: 0`; релевантные тесты зелёные.
