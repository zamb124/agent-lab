---
trigger: model_decision
description: "Глоссарий доменных имён платформы (flow, user_id, исключения)"
globs:
---

# Доменные имена (единый канон)

## Flow

**Flow** — исполняемый граф и конфигурация на платформе (узлы, рёбра, skills, переменные). В коде и API: `flow_id`, `FlowConfig`, `flow_repository`, префиксы ключей `flow:` в KV-хранилище service БД сервиса flows (`platform_agents`).

Тип ноды с LLM + tools в JSON конфиге: **`llm_node`** (класс `LlmNode`, раннер `apps/flows/src/runtime/runners/llm_runner.py`). Устаревшее имя **`react_node`** в конфигах не используется.

В схеме визуализации (`FlowFactory.get_flow_schema`) у llm-ноды вложенные flow, подключённые как tools, перечисляются в поле **`subflows`** (рекурсивно: `tools`, `subflows`), не `subagents`.

Mock-конфиг: `resolve_mock_config(..., flow_mock=..., ...)`. Ресурсы уровня flow в `ResourceResolver.resolve_for_node(flow_resources=...)`, не `agent_*`.

Документация кода (autocomplete): ракурс **`flow`**, не `agent` (в `core/docs/data/python/globals.py`).

Примеры в bundles: skill `direct_subflow`, нода `example_subflow`, evaluation `flow_dialog_test`, `inline_flows`; mock вложенных ответов — ключ **`flows`** (устаревший **`agents`** в `resolve_mock_config` мержится в `flows`).

Не смешивать с внешним «агентом» в смысле спецификации A2A (agent card, удалённый endpoint): там допустимы термины спеки, но платформенная сущность — **flow**.

## Пользователь

Идентификатор пользователя везде **`user_id`**, не голый `id` в моделях пользователя (например `UserBrief.user_id` в Sync API).

## Миграции схемы

Переименование колонок без пошаговых `ALTER`: в средах с допустимым сбросом данных — **удаление БД и `upgrade head`**, см. `migrations.mdc`.

## Исключения (не переименовывать слепо)

- **remote_flow**: тип ноды и A2A к внешнему endpoint (в спеке A2A по-прежнему agent-card и т.п.).
- **FlowInterrupt**, **Role.agent** (LLM): устоявшиеся имена рантайма.
- Поля внешних JSON по спецификациям (camelCase A2A), если спека фиксирует имя.
