# Матрица: тип триггера — что реально исполняется

Документ фиксирует **фактическое** поведение кода (проверяй при изменениях в `TriggerRegistry`, `triggers.py`, `TriggerExecutor`, `process_flow_task`).

## Легенда

| Колонка | Смысл |
|--------|--------|
| **HTTP /test** | `POST /flows/api/v1/flows/{flow_id}/triggers/{trigger_id}/test` — только `InputMapper` (`apps/flows/src/triggers/input_mapper.py`) + JSON ответ, **без** запуска flow и **без** `output_actions`. |
| **Инбанд вебхук** | Публичный URL в `apps/flows` для приёма события. |
| **TriggerExecutor** | `TriggerExecutor.execute` в `apps/flows/src/triggers/executor.py` — маппинг + `process_flow_task.kiq`. |
| **output_actions** | `OutputActionExecutor` в том же файле; вызов после завершения turn должен сходиться в канал/A2A — ищи по репозиторию `OutputActionExecutor` и по завершению `process_task`. |
| **TaskIQ** | `process_flow_task` в `apps/flows/src/tasks/flow_tasks.py` — выполнение агента. |

## Реестр `TriggerRegistry` (факт)

В `apps/flows/src/container.py` в реестр добавлен **только** `TriggerType.TELEGRAM` (`TelegramTriggerHandler`). Для `webhook`, `cron`, `email`, `redis` `get_handler` возвращает `None` — при `sync_triggers` триггер получает `status=error`, `last_error` про отсутствие handler, пока не добавят handler.

## По типу триггера (`TriggerType`)

| Тип | Регистрация (sync) | Вход: инбанд HTTP | HTTP /test | TriggerExecutor + TaskIQ | output_actions (рантайм) |
|-----|--------------------|--------------------|------------|----------------------------|----------------------------|
| `telegram` | `TelegramTriggerHandler`: `setWebhook`, `webhook_url` | `POST` Telegram webhook route — `TelegramTriggerHandler.handle` | маппинг с телом из запроса | `handle` → `TriggerExecutor` | после turn, если вызов подключён в канале |
| `webhook` | **Нет** handler в реестре (ошибка при sync) | `POST` `/flows/api/v1/triggers/webhook/{flow_id}/{trigger_id}` — см. `generic_webhook` | маппинг, без `output_actions` | когда роутер вызовет `TriggerExecutor` | когда подключено к завершению turn |
| `cron` / `email` / `redis` | **Нет** handler | зависит от будущей реализации | маппинг | — | — |

## Узкие места (сверка с UI)

1. Сохранение триггера = то, что в `FlowConfig.triggers` — **согласовано** с API.
2. «Тест» в UI: проверяй **sample JSON**; `{}` = только маппинг на пустом объекте.
3. `output_actions.condition`: канон `apps/flows/src/triggers/output_condition.py` (не Python `eval`); см. i18n «Вывод».
4. `generic_webhook` (`apps/flows/src/api/v1/triggers.py`): rate limit, `allowed_ips`, `secret_token` (заголовки `X-Trigger-Secret` / `X-Webhook-Secret` или query `secret`), усечённый лог ключей; исполнение flow — отдельно (пока может быть 501).
5. Ответы list/get create/update: поля `bot_token` / `secret_token` / пароли в `config` — `(redacted)` в JSON.

Обновляй матрицу, когда `generic_webhook` начнёт вызывать `TriggerExecutor` или когда `OutputActionExecutor` появится в цепочке после `process_task`.
