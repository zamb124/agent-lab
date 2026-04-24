---
trigger: always_on
description: "Runtime flows: ноды, tools, skills, FlowInterrupt, InterruptManager"
globs:
---
# Flows — краткий справочник

## NodeType (8 типов)

| Тип | Описание |
|-----|----------|
| llm_node | LLM + tools |
| code | Python код: execute(args, state) |
| flow | Вызов skill (flow_id + skill_id) |
| remote_flow | A2A вызов удалённого flow |
| external_api | HTTP запрос |
| mcp | MCP tool |
| channel | Отправка сообщений (Telegram, Webhook, Email) |
| hitl_node | Пауза до оператора очереди (`OperatorHandoffService`, `operator_task`) |

Очереди и задачи оператора: таблицы `operator_queues`, `operator_queue_members`, `operator_tasks` (БД flows), API **`/flows/api/v1/operator/...`**. Тул **`hitl_operator_task`** и нода **`hitl_node`** создают строку задачи и **`FlowInterrupt`** с **`OperatorTaskInterrupt`**; **`InterruptManager.apply_interrupt`** сохраняет опциональный **`correlation_id`**. Завершение: **`POST .../operator/tasks/{id}/complete`** → **`process_flow_task.kiq`** с **`is_resume=True`** и снимком контекста из задачи.

**Takeover user-reply через A2A (Section 3.4.3):** при `handoff_mode=takeover` реплики пользователя идут через штатный `message/stream` (A2A follow-up с тем же `taskId`/`contextId`). `BaseChannel._prepare_task_params` детектирует активный takeover по `state.interrupt` (`OperatorTaskInterrupt` + `HandoffMode.TAKEOVER` + `correlation_id` → задача в `CLAIMED`/`USER_DIALOG`) и устанавливает `is_takeover_user_reply=True`. `A2AChannel.on_message_stream` при этом флаге вызывает `receive_user_reply` → `dialog_log`, эмитит `input-required` и завершает SSE. Отдельного REST-эндпоинта для user-reply нет — всё через A2A.

**dialog_log при complete_handoff:** содержимое `dialog_log` НЕ мержится в `state.messages` (это ломает tool_call/tool_result паринг OpenAI API). Вместо этого `_format_dialog_log_for_tool_result` форматирует лог как текст, который передаётся агенту в `content` при resume. Каждая запись `dialog_log` может содержать опциональное поле `file_ids: list[str]` — ID файлов из `FileRecord`; при форматировании добавляются download-ссылки.

**Файловые вложения в HITL:** оператор и пользователь могут прикреплять файлы в обоих режимах. API `POST /tasks/{id}/messages` и `POST /tasks/{id}/complete` принимают `file_ids: list[str]`. Файлы загружаются через `POST /flows/api/v1/files/` (multipart), ID передаются в body. `OperatorHandoffService` валидирует `file_ids` через `FileRepository.get` (несуществующий файл → `ValueError`). При takeover: `emit_file_artifact` публикует артефакт `operator_files` (DataPart с `file_ids`) в Redis PubSub. Юзер при takeover может отправлять `FilePart` через A2A `message/send`; `_handle_takeover_user_reply` сохраняет файлы через `FileProcessor` и добавляет `file_ids` в `dialog_log`.

**`HandoffMode`** (StrEnum, `core/state/interrupt.py`): **`single_reply`** — оператор видит одно поле + кнопку «ответить», текст = tool result, карточка закрывается; **`takeover`** — полный перехват диалога, оператор общается с пользователем в workbench, по завершению `dialog_log` мержится в `ExecutionState.messages`. Режим задаётся при вызове тула (`handoff_mode` в `HitlOperatorTaskArgs`) или в конфиге ноды (`operator_handoff_mode` в `NodeConfig`), сохраняется в `operator_tasks.interrupt_snapshot.handoff_mode`. API: `POST /messages` доступен только при `takeover` (403 при `single_reply`); `POST /tasks/{id}/user-reply` — ответ пользователя оператору при takeover; `POST /complete` единый для обоих режимов.

**`hitl_node` и `input_mapping`:** резолвятся в `inputs` до чтения полей конфига; приоритет у маппинга. Параметры: **`assignee_queue`** (slug очереди), **`task_title`**, **`user_facing_message`** или **`question`** (текст пользователю), **`handoff_mode`** (`single_reply` | `takeover`). Fallback в конфиге: **`operator_queue_slug`**, опционально **`operator_queue_id`** (UUID → slug в рантайме), **`operator_task_title`**, **`operator_user_message`**, **`operator_handoff_mode`**.

## Любая нода = Tool

NodeAsToolWrapper оборачивает ЛЮБУЮ ноду для LlmNode; `BaseNode.as_tool()` возвращает тот же класс через `NodeAsToolWrapper.from_base_node` (отдельного `NodeAsTool` нет):

    tools: [
      {"tool_id": "calc", "type": "code", "code": "..."},
      {"tool_id": "skill", "type": "flow", "flow_id": "self", "skill_id": "math"},
      {"tool_id": "api", "type": "external_api", "url": "..."},
    ]

## LlmNode - параллельное выполнение

LLM возвращает несколько tool_calls → asyncio.gather → все выполняются параллельно.

Merge:
- messages → extend (все добавляются)
- tool_results → merge (все результаты)
- остальное → last wins

## LlmNode — контекст для LLM (`messages_filter`)

- Конфиг ноды: `messages_filter`: `"all"` | `"own"` | `list[node_id]` (см. `NodeConfig`). Задаёт **какие сообщения из `state.messages` передаются в модель**; полный лог в `state.messages` **не режется**.
- Режимы `own` и список учитывают **только** `metadata.node_id` (и user, и agent). Сообщения другой ноды с `role=user` в срез не попадают — иначе при нескольких LLM-нодах дублировался бы один и тот же ввод.
- Новые реплики ReAct пишутся в **`state.messages`** с `metadata.node_id` = `node_id` этой `llm_node`.
- `FlowValidator`: элементы списка `messages_filter` должны быть **существующими** `node_id` графа.

## BaseNode — фильтрация для прочих нод

- `messages_filter` в dict-конфиге ноды + `_get_filtered_messages()` (используется не только LLM). Недопустимое значение → `ValueError` (без тихого fallback на «все сообщения»).

## CodeNode

    def execute(args, state):
        state.result = args['value'] * 2
        return {'result': state.result}

Последняя функция в коде = entry point.

## Маппинги

input_mapping - откуда берём данные:

    input_mapping: {
        "query": "@state:user_query",   # из state.user_query
        "limit": "@const:10",           # константа
    }

output_mapping - куда пишем результат:

    output_mapping: {
        "result": "calculation_result"  # result → state.calculation_result
    }

## Skills как Tools

Один flow может вызывать свои skills как tools:

    {
        "tool_id": "my_skill",
        "type": "flow",
        "flow_id": "self_flow",  // тот же flow
        "skill_id": "math_skill",
        "args_schema": {"x": {"type": "integer"}}
    }

## Структура FlowConfig

    {
      "flow_id": "my_flow",
      "entry": "main",
      "nodes": {
        "main": {"type": "llm_node", "prompt": "...", "tools": [...]}
      },
      "edges": [{"from_node": "main", "to_node": null}],
      "skills": {
        "math_skill": {"name": "Math", "entry": "calc", "nodes": {...}}
      }
    }

## Fan-in: `incoming_policy` и ребро `contributes_to_join`

- У ноды с **несколькими входящими** рёбрами в конфиге ноды: `incoming_policy`: `"any"` (по умолчанию) | `"all"`.
- **`any`**: нода ставится в волну при завершении **любого** входящего ребра (как раньше).
- **`all`**: AND-join — нода ждёт, пока по всем релевантным предшественникам придут завершения; учёт в `state.join_arrived_preds`, сброс после выполнения ноды.
- На ребре: `contributes_to_join` (по умолчанию `true`) — участвует ли ребро в join для целевой ноды.
- В редакторе flows: иконка ANY/ALL только при **≥ 2** входящих рёбрах; оверлей в DOM внутри `.inputs` над `.input`, `pointer-events: none`; модалка — двойной щелчок по порту или пункт контекстного меню ноды (пункт всегда в меню: неактивен/серый при одном или нуле входящих связей, с подсказкой в `title`). Точка входа может иметь входящий порт.

## Завершение flow (терминал)

- Тихий выход из цикла без следующей волны **недопустим**, если остался незакрытый AND-join (`state.join_arrived_preds` не пуст) → `FlowPrematureCompletionError` (`incomplete_and_join`).
- Если у завершившейся ноды есть **исходящие рёбра к нодам** (`to` не `null`) и **ни одно** не активно, причём **все** эти рёбра **с** условием — `FlowPrematureCompletionError` (`no_conditional_match`, в `payload` есть `stuck_at`). Нужны явные ветки, покрывающие сценарии (второе условие, отдельная default-нода, перенос ветвления в code-ноде).
- В смешанном случае (часть рёбер без `condition` к `to` не `null`, но нет ни одного активного перехода) — `FlowPrematureCompletionError` (`no_active_outgoing_edge`).

## Triggers (точки входа)

Триггеры запускают flow из внешних источников:

| Тип | Описание |
|-----|----------|
| telegram | Webhook от Telegram бота |
| webhook | HTTP POST запрос |
| cron | Расписание (TaskIQ) |

    "triggers": {
      "tg": {
        "type": "telegram",
        "config": {"bot_token": "@var:bot_token"},
        "input_mapping": {"content": "@trigger:message.text"},
        "output_actions": [...]
      }
    }

## ChannelNode (отправка сообщений)

    {
      "type": "channel",
      "channel": "telegram",  // telegram, webhook
      "action": "send_message",
      "channel_config": {"bot_token": "..."},
      "input_mapping": {"recipient": "@state:chat_id", "text": "@state:response"}
    }

Как tool в LlmNode:

    {"tool_id": "notify", "type": "channel", "channel": "webhook", ...}

## FlowInterrupt - Механизм Прерывания

Бросает `FlowInterrupt(question="...")` или `FlowInterrupt(body=UserMessageInterrupt(...)|OperatorTaskInterrupt(...)|OAuthInterrupt(...))` → выполнение останавливается → в `state.interrupt` попадает типизированный `InterruptData` (`body` + `system`).

**OAuth auto-resume:** `OAuthInterrupt` (kind=`oauth_required`) с `auth_url`, `provider`, `service`. SSE `input-required` с `final=False`, `platform_oauth_continue=true`. После OAuth callback — `process_flow_task.kiq(is_resume=True, content="oauth_completed:...")` (по аналогии с `complete_handoff`). UI показывает кнопку авторизации; flow продолжается автоматически без участия юзера.

### State при interrupt

    state.interrupt: InterruptData          # body (union) + system (конверт)
    state.interrupt_path: List[PathItem]    # Путь к месту прерывания
    state.nested_states: Dict[str, Data]    # Состояния вложенных вызовов (skills/tools)
    state.current_nodes: List[str]          # Где остановились на графе

### Сценарий 1: ask_user tool в LlmNode

    LlmNode → ask_user → FlowInterrupt
    
- `interrupt_path = [{type: "tool", id: "ask_user"}]`
- Resume: ответ → tool result в messages → LLM продолжает

### Сценарий 2: ask_user во вложенном llm_node (как tool)

    LlmNode → child_flow (llm_node tool) → ask_user → FlowInterrupt
    
- `interrupt_path = [{type: "llm_node", id: "child_flow"}, {type: "tool", id: "ask_user"}]`
- `nested_states["child_flow"]` = сохранённое состояние child
- Resume: по `interrupt_path[0]` → загрузить nested_state → передать ответ → child продолжает

### Сценарий 3: FlowNode (subflow на графе) с CodeNode

    Parent flow → FlowNode("call_child") → Child flow → CodeNode → FlowInterrupt
    
- FlowNode - это нода на графе (type: "flow"), не tool!
- `current_nodes = ["call_child"]` - где остановились
- CodeNode может бросить `raise FlowInterrupt(question="...")` 
- Resume: `Flow.run()` видит `interrupt + content` → продолжает с `current_nodes`
- FlowNode вызывается повторно, передаёт `state.content` (ответ) в child

### Сценарий 4: FlowNode с LlmNode + ask_user

    Parent (LlmNode tool) → child_flow → LlmNode → ask_user
    
- Комбинация сценариев 2 и 3
- `interrupt_path` содержит путь: `[child_flow, ask_user]`
- `nested_states["child_flow"]` хранит историю messages
- Resume: ответ попадает как tool result в messages child → LLM child продолжает

### Как бросить interrupt

В CodeNode/tool:

    from apps.flows.src.runtime.exceptions import FlowInterrupt
    raise FlowInterrupt(question="Как вас зовут?")

Или использовать готовую функцию:

    from apps.flows.src.eval.state_utils import ask_user
    ask_user("Как вас зовут?")

### Ключевые компоненты

- `InterruptManager.save_nested_state()` - сохраняет state
- `InterruptManager.load_nested_state()` - загружает при resume
- `InterruptManager.push_interrupt_path()` - добавляет в НАЧАЛО пути
- `InterruptManager.apply_interrupt()` - единая запись `InterruptData` в state
- `InterruptManager.enrich_system_from_channel()` - task_id/context_id после run в канале
- `Flow.run()` - определяет resume по `state.interrupt + state.content`

### Merge при interrupt

- `messages` - extend
- `nested_states` - update напрямую
- `interrupt_path` - копируется целиком
- остальное - last wins

## Ключевые файлы

- apps/flows/src/runtime/nodes.py - все ноды
- apps/flows/src/runtime/runners/llm_runner.py - LlmNode логика
- apps/flows/src/tools/node_wrapper.py - NodeAsToolWrapper (interrupt для вложенных flow)
- apps/flows/src/tools/registry.py - ToolRegistry
- apps/flows/src/state/interrupt_manager.py - InterruptManager
- apps/flows/src/triggers/ - триггеры (handlers, executor, registry)
- apps/flows/src/channels/ - каналы (telegram.py, webhook.py)
- core/state/__init__.py - ExecutionState, NestedStateData
- core/state/interrupt.py - InterruptKind, union тел, InterruptData
