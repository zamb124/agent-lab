# Матрица: тип триггера — что реально исполняется

Документ фиксирует **фактическое** поведение кода (проверяй при изменениях в `TriggerRegistry`, `triggers.py`, `TriggerExecutor`, `process_flow_task`).

## Легенда

| Колонка | Смысл |
|--------|--------|
| **HTTP /test** | `POST /flows/api/v1/flows/{flow_id}/triggers/{trigger_id}/test` — только `InputMapper` (`apps/flows/src/triggers/input_mapper.py`) + JSON ответ, **без** запуска flow и **без** `output_actions`. |
| **Инбанд вебхук** | Публичный URL в `apps/flows` для приёма события. |
| **TriggerExecutor** | `TriggerExecutor.execute` в `apps/flows/src/triggers/executor.py` — маппинг + `process_flow_task.kiq`. |
| **output_actions** | `OutputActionExecutor` в `apps/flows/src/triggers/executor.py`; вызов из `BaseChannel.process_task` после успешного `runtime_flow.run` (без interrupt, без breakpoint), если в `metadata` есть `trigger_id` и в триггере разрешён пост-выход (`post_flow_output_enabled`, контракт по типу в `trigger_type_contract.py`, эффективный список — `effective_output_actions_for_trigger`). |
| **TaskIQ** | `process_flow_task` в `apps/flows/src/tasks/flow_tasks.py` — выполнение агента. |

## `state.triggers` (рантайм)

- Ключ — **`trigger_id`** (в рамках flow уникален; несколько триггеров одного `TriggerType` различаются по id).
- Значение — снимок `TriggerRuntimeSnapshot`: **`payload`** (сырой вход) и **`context`** (поля из маппинга триггера: `context.*` слева).
- `state.variables` — только бизнес-данные flow (`@var:`, ...); **не** для полей из входа триггера. В маппинге триггера путь `variables.*` **запрещён** (валидация `TriggerConfig`).
- Дефолтный `recipient` для ответа в тот же Telegram-чат: `@state:triggers.<trigger_id>.context.chat_id` (подставляется при пустом списке `output_actions` на create).

## Реестр `TriggerRegistry` (факт)

В `apps/flows/src/container.py` в реестр добавлен **только** `TriggerType.TELEGRAM` (`TelegramTriggerHandler`). Для `webhook`, `cron`, `email`, `redis` `get_handler` возвращает `None` — при `sync_triggers` триггер получает `status=error`, `last_error` про отсутствие handler, пока не добавят handler.

## По типу триггера (`TriggerType`)

| Тип | Регистрация (sync) | Вход: инбанд HTTP | HTTP /test | TriggerExecutor + TaskIQ | output_actions (рантайм) |
|-----|--------------------|--------------------|------------|----------------------------|----------------------------|
| `telegram` | `TelegramTriggerHandler`: `setWebhook`, `webhook_url` | `POST` Telegram webhook route — `TelegramTriggerHandler.handle` | маппинг с телом из запроса | `handle` → `TriggerExecutor` | `process_task` → `OutputActionExecutor` при включённой рассылке |
| `webhook` | **Нет** handler в реестре (ошибка при sync) | `POST` `/flows/api/v1/triggers/webhook/{flow_id}/{trigger_id}` — см. `generic_webhook` | маппинг, без `output_actions` | когда роутер вызовет `TriggerExecutor` | `process_task` → `OutputActionExecutor` при включённой рассылке |
| `cron` / `email` / `redis` | **Нет** handler | зависит от будущей реализации | маппинг | — | для `cron` пост-выход выключен по контракту; `email`/`redis` — как только вход завершён через `process_task` с `trigger_id` |

## Узкие места (сверка с UI)

1. Сохранение триггера = то, что в `FlowConfig.triggers` — **согласовано** с API.
2. «Тест» в UI: проверяй **sample JSON**; `{}` = только маппинг на пустом объекте.
3. `output_actions.condition`: канон `apps/flows/src/triggers/output_condition.py` (не Python `eval`); см. i18n «Вывод».
4. `generic_webhook` (`apps/flows/src/api/v1/triggers.py`): rate limit, `allowed_ips`, `secret_token` (заголовки `X-Trigger-Secret` / `X-Webhook-Secret` или query `secret`), усечённый лог ключей; исполнение flow — отдельно (пока может быть 501).
5. Ответы list/get create/update: поля `bot_token` / `secret_token` / пароли в `config` — `(redacted)` в JSON.
6. `post_flow_output_enabled` в `TriggerConfig` и `effective_output_actions_for_trigger` определяют, подставляются ли дефолтные `output_actions` в API и выполняется ли `OutputActionExecutor` после `process_task` для данного типа.
