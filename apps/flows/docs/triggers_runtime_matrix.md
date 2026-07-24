# Матрица: тип триггера — что реально исполняется

Документ фиксирует **фактическое** поведение кода (проверяй при изменениях в `TriggerRegistry`, `triggers.py`, `TriggerExecutor`, `process_flow_task`).

## Легенда

| Колонка | Смысл |
|--------|--------|
| **HTTP /test** | `POST /flows/api/v1/flows/{flow_id}/triggers/{trigger_id}/test` — только `InputMapper` (`apps/flows/src/triggers/input_mapper.py`) + JSON ответ, **без** запуска flow и **без** `output_actions`. |
| **Инбанд вебхук** | Публичный URL в `apps/flows` для приёма события. |
| **TriggerExecutor** | `TriggerExecutor.execute` в `apps/flows/src/triggers/executor.py` — маппинг + `enqueue(TASK_PROCESS_FLOW, ...)`. |
| **output_actions** | `OutputActionExecutor` в `apps/flows/src/triggers/executor.py`; вызов из `BaseChannel.process_task` после успешного `runtime_flow.run` (без interrupt, без breakpoint), если в `metadata` есть `trigger_id` и в триггере разрешён пост-выход (`post_flow_output_enabled`, контракт по типу в `trigger_type_contract.py`, эффективный список — `effective_output_actions_for_trigger`). |
| **TaskIQ** | `process_flow_task` в `apps/flows/src/tasks/flow_tasks.py` — выполнение агента. |
| **completed assert** | Integration e2e: `workflow_runtime.get_state(session_id)` → `terminal_task_state == "completed"` (MockLLM only). |
| **output_actions e2e** | Integration e2e: inbound/dispatch → completed → HTTP notify на `NotificationServer`. |

## `state.triggers` (рантайм)

- Ключ — **`trigger_id`** (в рамках flow уникален; несколько триггеров одного `TriggerType` различаются по id).
- Значение — снимок `TriggerRuntimeSnapshot`: **`payload`** (сырой вход) и **`context`** (поля из маппинга триггера: `context.*` слева).
- `state.variables` — только бизнес-данные flow (`@var:`, ...); **не** для полей из входа триггера. В маппинге триггера путь `variables.*` **запрещён** (валидация `TriggerConfig`).
- Дефолтный `recipient` для ответа в тот же Telegram-чат: `@state:triggers.<trigger_id>.context.chat_id` (подставляется при пустом списке `output_actions` на create).

## Реестр `TriggerRegistry` (факт)

В `apps/flows/src/container.py` в реестр добавлены `TriggerType.TELEGRAM` (`TelegramTriggerHandler`), `TriggerType.WEBHOOK` (`WebhookTriggerHandler`), `TriggerType.EMAIL` (`EmailTriggerHandler`) и `TriggerType.PLATFORM_EVENT` (`PlatformEventTriggerHandler`). Для `cron` `get_handler` возвращает `None` — при `sync_triggers` триггер получает `status=error`, `last_error` про отсутствие handler, пока не добавят handler.

## По типу триггера (`TriggerType`)

| Тип | Регистрация (sync) | Вход: инбанд HTTP | HTTP /test | TriggerExecutor + TaskIQ | output_actions (рантайм) | completed assert | output_actions e2e |
|-----|--------------------|--------------------|------------|----------------------------|----------------------------|------------------|--------------------|
| `telegram` | `TelegramTriggerHandler`: `setWebhook`/`deleteWebhook` уважают `config.api_base`; `webhook_url` | `POST` Telegram webhook route — `TelegramTriggerHandler.handle` | маппинг с телом из запроса | `handle` → `TriggerExecutor` | `process_task` → `OutputActionExecutor` при включённой рассылке | yes (`test_triggers` full webhook e2e) | yes (Telegram → channel notify) |
| `webhook` | `WebhookTriggerHandler`: `webhook_url`, `status=active` | `POST` `/flows/api/v1/triggers/webhook/{flow_id}/{trigger_id}` — envelope `{body,headers,query}` → `WebhookTriggerHandler.handle` → **202** `{status,task_id,context_id,session_id}` | маппинг, без `output_actions` | `handle` → `TriggerExecutor` | `process_task` → `OutputActionExecutor` при включённой рассылке | yes (`test_webhook_trigger_inbound`) | yes (callback → `NotificationServer`) |
| `email` | `EmailTriggerHandler`: Redis `SADD flows:email_triggers:{mailbox_binding_id}` | нет HTTP; `mail_sync_tick` **и** `mail_sync_binding_task` → `dispatch_email_triggers_for_messages` (deterministic `task_id`/`context_id` из binding+flow+trigger+uid) | маппинг | dispatch → `TriggerExecutor` | `process_task` → `OutputActionExecutor` при включённой рассылке | yes (`test_email_trigger_inbound`) | — |
| `platform_event` | `PlatformEventTriggerHandler`: Redis `SADD flows:event_triggers:{event_type}` | нет HTTP; consumer group `flows` (`PlatformEventConsumerService.handle_event`) → `dispatch_platform_event_triggers` | маппинг | dispatch → `TriggerExecutor` (deterministic `task_id`/`context_id` из `event_id + trigger_id`) | пост-выход выключен по контракту (как `cron`) | yes (`test_platform_event_filters_e2e`) | N/A (контракт) |
| `cron` | **Нет** handler | зависит от будущей реализации | маппинг | — | пост-выход выключен по контракту | sync→error only | — |

## Узкие места (сверка с UI)

1. Сохранение триггера = то, что в `FlowConfig.triggers` — **согласовано** с API.
2. «Тест» в UI редактора: кнопка sample→`POST .../test` (disabled до save); list-modal — свой sample JSON.
3. `output_actions.condition`: канон `apps/flows/src/triggers/output_condition.py` (не Python `eval`); см. i18n «Вывод».
4. `generic_webhook` (`apps/flows/src/api/v1/triggers.py`): rate limit, `allowed_ips`, `secret_token` + `secret_header` (заголовок из конфига или query `secret`), envelope `{body, headers, query}`, `TriggerExecutor` → HTTP 202 с `session_id`/`context_id`.
5. Ответы list/get create/update: поля `bot_token` / `secret_token` / пароли в `config` — `(redacted)` в JSON.
6. Email UI: platform mailbox (`mailbox_binding_id`) + optional filter; без ручного IMAP. Verify — binding принадлежит user + connection `active`.
7. `post_flow_output_enabled` в `TriggerConfig` и `effective_output_actions_for_trigger` определяют, подставляются ли дефолтные `output_actions` в API и выполняется ли `OutputActionExecutor` после `process_task` для данного типа.
8. Mapping UI: клик по примеру добавляет пару `state → payload` (пути webhook относительно envelope); how-to для email / platform_event / cron.
9. Telegram verify/register: `get_telegram_api_base(config)` — единый override `api_base` (тесты через `NotificationServer`).
