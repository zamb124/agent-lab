"""
Глобальные переменные для Python inline кода.
"""

from typing import Any, Dict, List

# Глобальные переменные с поддержкой perspectives
GLOBALS: List[Dict[str, Any]] = [
    # State - главная сущность
    {
        "name": "state",
        "type": "ExecutionState",
        "doc": (
            "Состояние выполнения `run(state)`; доступ как к dict: `state['content']`, `state.get('key')`.\n\n"
            "- **`task_id`**, **`context_id`**, **`user_id`**, **`session_id`** — обязательные системные поля (не менять из кода ноды/tool)\n"
            "- **`content`** — вход пользователя; **`response`** — ответ агента; **`result`** — результат ноды/tool\n"
            "- **`messages`** — `List[Message]`; **`files`** — список вложений `{name, path, mime_type, ...}`\n"
            "- **`user_groups`**, **`variables`**, **`current_nodes`** — группы, переменные flow, активные ноды (только чтение для `user_groups`/`current_nodes` из user-кода)\n"
            "- **`flow_deadline_monotonic`**, **`flow_timeout_effective_seconds`** — дедлайн wall-clock одного run flow (системные, не трогать из кода)\n"
            "- заморозка полей: `core/state/mutation_policy.py` (`FROZEN_STATE_FIELDS`); нарушение — `FrozenStateFieldError`\n"
            "- дополнительные поля через присваивание (вне заморозки); сериализация: `state.model_dump()`"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["core", "data"],
    },
    # LLM клиент
    {
        "name": "llm",
        "type": "SafeLLMClient",
        "doc": (
            "await llm.chat(messages, *, response_model=None, tools=None, model=None, "
            "temperature=None, top_p=None, top_k=None, max_tokens=None, "
            "frequency_penalty=None, presence_penalty=None, seed=None, reasoning_effort=None, "
            "extra_body=None).\n"
            "Аргумент messages: str | list[str] | Message | list[Message] | dict | list[dict] "
            "(роли/контент нормализуются рантаймом).\n"
            "Возврат: Message (текст, tool_calls в metadata) или экземпляр response_model при structured output.\n"
            "- model — имя модели; response_model — Pydantic-модель для structured output\n"
            "- tools — OpenAI dict ИЛИ результат @tool(...) / BaseTool с to_openai_schema(); сырую def без @tool нельзя\n"
            "- temperature, top_p, top_k, max_tokens, frequency_penalty, presence_penalty\n"
            "- seed, reasoning_effort; extra_body — dict полей тела запроса к провайдеру (мерж последним)\n"
            "Текст: from a2a.utils.message import get_message_text; get_message_text(msg)"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["llm", "ai"],
    },
    {
        "name": "tool",
        "type": "decorator",
        "doc": (
            "Декоратор для функции, которую нужно отдать в llm.chat(..., tools=[...]).\n"
            "@tool(name='add', description='Складывает a и b', tags=['math'])\n"
            "def add(a: int, b: int): return a + b\n"
            "После этого add — экземпляр BaseTool; схема аргументов из аннотаций (state в сигнатуре не попадает в JSON schema).\n"
            "Вызов: await llm.chat('сколько 3+4?', tools=[add]). Ответ может содержать tool_calls в metadata; исполнить логику тула вручную (например await add.run(args, state)) или свой ReAct-цикл — платформа внутри одного llm.chat цикл не крутит."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["llm", "tools"],
    },
    # Контекст и канал
    {
        "name": "context",
        "type": "SafeContext",
        "doc": (
            "Контекст выполнения (только чтение):\n"
            "- context.channel - канал (a2a, api, telegram, max, voip; без контекста — 'unknown')\n"
            "- context.user_id - ID пользователя\n"
            "- context.session_id - ID сессии\n"
            "- context.flow_id - ID агента\n"
            "- context.metadata - dict с метаданными"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["context", "runtime"],
    },
    {
        "name": "channel",
        "type": "SafeChannel",
        "doc": (
            "Канал для отправки сообщений пользователю:\n"
            "- await channel.send('Текст сообщения')\n"
            "- await channel.send_with_buttons('Выберите:', ['Да', 'Нет'])"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["channel", "communication"],
    },
    {
        "name": "variables",
        "type": "dict",
        "doc": "Переменные агента (только для чтения). Доступ: variables['key'] или variables.get('key', default)",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["variables", "data"],
    },
    {
        "name": "logger",
        "type": "Logger",
        "doc": (
            "Логгер для отладки:\n"
            "- logger.info('Сообщение')\n"
            "- logger.warning('Предупреждение')\n"
            "- logger.error('Ошибка', exc_info=True)"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["logging", "debug"],
    },
    # State утилиты (базовые)
    {
        "name": "deep_copy_state",
        "type": "function",
        "doc": "Глубокое копирование state:\ncopy = deep_copy_state(state)",
        "perspectives": ["editor", "flow", "node"],
        "tags": ["state", "utility"],
    },
    {
        "name": "merge_state",
        "type": "function",
        "doc": "Объединение двух state (глубокий merge):\nresult = merge_state(base_state, updates)",
        "perspectives": ["editor", "flow", "node"],
        "tags": ["state", "utility"],
    },
    {
        "name": "get_nested",
        "type": "function",
        "doc": (
            "Получить вложенное значение по пути:\n"
            "- get_nested(state, 'user.profile.name')\n"
            "- get_nested(state, 'data.items', default=[])"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["state", "utility"],
    },
    {
        "name": "set_nested",
        "type": "function",
        "doc": "Записать значение по пути (мутирует state, тот же объект возвращается):\nset_nested(state, 'user.name', 'Иван')",
        "perspectives": ["editor", "flow", "node"],
        "tags": ["state", "utility"],
    },
    # State утилиты (расширенные)
    {
        "name": "get_files",
        "type": "function",
        "doc": "Получить файлы из state:\nfiles = get_files(state)\n# -> [{name, path, mime_type, size}, ...]",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["files", "utility"],
    },
    {
        "name": "find_file",
        "type": "function",
        "doc": (
            "Найти файл по имени в списке state.files:\n"
            "finfo = find_file(get_files(state), 'report.docx')\n\n"
            "Без имени — последний файл из списка (обычно последняя загрузка):\n"
            "finfo = find_file(get_files(state))\n\n"
            "Поиск: точное совпадение по полю name, затем case-insensitive подстрока.\n"
            "Возвращает dict записи файла или None."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["files", "utility"],
    },
    {
        "name": "reader",
        "type": "FileReader",
        "doc": (
            "Метод read(source, *, file_name=None, include_asset_bytes=False, source_file_id=None, source_checksum=None, "
            "vision_model=..., vision_prompt=None) — все именованные аргументы необязательны, кроме смысла source.\n\n"
            "source — одно из:\n"
            "• запись вложения: dict из get_files(state) / state.files, или FileRecord / FileResponse (path и/или file_id / url);\n"
            "• строка пути к файлу на диске, pathlib.Path, или bytes уже загруженного файла.\n\n"
            "Удобнее всего передать целиком объект вложения:\n"
            "f = get_files(state)[0]\n"
            "res = await reader.read(f)\n\n"
            "Для source=bytes обязателен file_name с расширением (.pdf, .docx, .png …).\n"
            "Для source=str(path) без записи вложения лучше явно file_name=..., чтобы тип совпал с файлом.\n\n"
            "Именованные параметры: include_asset_bytes (PDF, тяжёлый ответ), source_file_id и source_checksum, "
            "vision_prompt / vision_model для картинок (пустую строку в vision_prompt нельзя).\n\n"
            "Результат FileReadResult: pages, page_count, detected_kind, mime_type, warnings, source_checksum, source_file_id.\n"
            "detected_kind: text, html (.html/.htm и MIME text/html — извлечение через trafilatura в markdown), pdf, office, spreadsheet, image, audio, video, unknown.\n"
            "Тип по имени/заголовку: reader.recognize_file_type(file_name='x.png', head=raw[:8192]).\n"
            "Без кода: tool read_file."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["files", "reader"],
    },
    {
        "name": "writer",
        "type": "FileWriter",
        "doc": (
            "writer = FileWriter() в namespace процесса flows: на старте FileWriter.configure_process_upload — дальше "
            "await writer.write(...) в хранилище. build_bytes — только сборка в память.\n\n"
            "await writer.write(content=..., original_name=..., content_mode='auto', public=True, "
            "text_encoding='utf-8', max_image_bytes=..., http_timeout_seconds=..., pdf_max_image_width_pt=..., "
            "docx_image_width_inches=...) -> FileMetadata.\n"
            "create_file(...) с явным WriteOptions оставлен для редких случаев в коде вне eval.\n\n"
            "build_bytes(content, original_name, content_mode='auto', options=None) -> FileWriteResult (data, mime_type, ...).\n\n"
            "content: str или bytes. content_mode: auto | markdown | base64 | raw.\n\n"
            "Пример: meta = await writer.write(content='# Отчёт\\n|A|B|\\n|-|-|\\n|1|2|', original_name='t.xlsx', "
            "content_mode='markdown')\n\n"
            "Tool create_file — тот же сценарий без кода."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["files", "writer"],
    },
    {
        "name": "get_user",
        "type": "function",
        "doc": "Сводка из state:\nuser = get_user(state)\n# -> {id, groups} (groups из user_groups)",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["user", "utility"],
    },
    {
        "name": "get_tool_result",
        "type": "function",
        "doc": "Получить результат выполнения tool:\nresult = get_tool_result(state, 'calculator')",
        "perspectives": ["editor", "flow", "node"],
        "tags": ["tools", "utility"],
    },
    {
        "name": "get_messages",
        "type": "function",
        "doc": "Получить историю сообщений:\nmessages = get_messages(state)\n# -> List[Message]",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["messages", "utility"],
    },
    {
        "name": "add_user_message",
        "type": "function",
        "doc": "Добавить сообщение пользователя в историю:\nstate = add_user_message(state, 'Текст')",
        "perspectives": ["editor", "flow", "node"],
        "tags": ["messages", "utility"],
    },
    {
        "name": "add_agent_message",
        "type": "function",
        "doc": "Добавить сообщение агента в историю:\nstate = add_agent_message(state, 'Ответ агента')",
        "perspectives": ["editor", "flow", "node"],
        "tags": ["messages", "utility"],
    },
    {
        "name": "push_ui_event",
        "type": "function",
        "doc": (
            "Поставить одно UI-событие в очередь state для стрима:\n"
            "push_ui_event(state, 'action_invoked', {'action_id': 'flows.node.patch.apply', 'action_kind': 'apply'}, "
            "event_id='evt-1', version='1.0.0', source='assistant', correlation_id='corr-1')\n"
            "Событие уходит в A2A как artifact.name='ui_event'."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["ui", "events", "streaming"],
    },
    {
        "name": "push_ui_events",
        "type": "function",
        "doc": (
            "Поставить несколько UI-событий (список dict):\n"
            "push_ui_events(state, [\n"
            "  {'type': 'action_previewed', 'payload': {...}, 'version': '1.0.0'},\n"
            "  {'type': 'navigate', 'payload': {...}},\n"
            "])"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["ui", "events", "streaming"],
    },
    {
        "name": "pop_ui_events",
        "type": "function",
        "doc": (
            "Извлечь и очистить очередь UI-событий из state:\n"
            "events = pop_ui_events(state)\n"
            "# -> [{'id','type','payload','version','timestamp','source','correlation_id'}, ...]"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["ui", "events", "streaming"],
    },
    # Interrupt
    {
        "name": "ask_user",
        "type": "function",
        "doc": (
            "Синхронный запрос пользователю (interrupt):\nask_user('Как вас зовут?')\n"
            "Для await llm.chat(..., tools=[...]) передай в списке tools имя ask_user_tool."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["interrupt", "interaction"],
    },
    {
        "name": "ask_user_tool",
        "type": "tool",
        "doc": (
            "Готовый tool для LLM: await llm.chat('...', tools=[ask_user_tool]). "
            "Прямой вопрос пользователю из тела кода ноды — вызов ask_user(...)."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["interrupt", "llm", "tools"],
    },
    {
        "name": "Встроенные tools",
        "type": "convention",
        "doc": (
            "В окружении кода ноды по имени доступны встроенные tools платформы: calculator, read_file, create_file, "
            "rag_create_namespace, rag_add_text, rag_search, pravo_catalog_search, pravo_document_rag_search, "
            "а для каталога IPS (POST search.json) и загрузки НПА также доступны PravoClient и PravoClientError, "
            "reason, final_answer, finish, self_check, задачи планировщика (schedule_*), … "
            "Новый системный tool подключается разработчиками платформы в реестр пакета tools."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["tools", "platform"],
    },
    # Interrupt-типы
    {
        "name": "FlowInterrupt",
        "type": "exception",
        "doc": (
            "Прерывание выполнения flow:\n"
            "raise FlowInterrupt(question='Как вас зовут?')\n\n"
            "Для operator handoff:\n"
            "raise FlowInterrupt(body=OperatorTaskInterrupt(question=..., task_title=..., assignee_queue=..., handoff_mode=HandoffMode.single_reply))\n\n"
            "После ответа пользователя / оператора flow продолжается с того же места."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["interrupt", "exception"],
    },
    {
        "name": "HandoffMode",
        "type": "enum",
        "doc": (
            "Режим передачи оператору:\n"
            "- HandoffMode.single_reply — один ответ оператора\n"
            "- HandoffMode.takeover — полный перехват диалога оператором"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["interrupt", "operator"],
    },
    {
        "name": "InterruptKind",
        "type": "enum",
        "doc": (
            "Вид прерывания:\n"
            "- InterruptKind.user_input — запрос ввода от пользователя\n"
            "- InterruptKind.operator_task — передача оператору\n"
            "- InterruptKind.oauth_required — ожидание OAuth-авторизации"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["interrupt", "types"],
    },
    {
        "name": "UserMessageInterrupt",
        "type": "class",
        "doc": (
            "Тело interrupt для запроса у пользователя:\n"
            "raise FlowInterrupt(body=UserMessageInterrupt(question='Ваш email?'))"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["interrupt", "types"],
    },
    {
        "name": "OperatorTaskInterrupt",
        "type": "class",
        "doc": (
            "Тело interrupt для передачи оператору:\n"
            "raise FlowInterrupt(body=OperatorTaskInterrupt(\n"
            "    question='Клиент запрашивает возврат',\n"
            "    task_title='Возврат заказа #123',\n"
            "    assignee_queue='support',\n"
            "    handoff_mode=HandoffMode.takeover,\n"
            "))"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["interrupt", "operator"],
    },
    # Интеграции
    {
        "name": "ServiceClient",
        "type": "class",
        "doc": (
            "HTTP между сервисами (заголовки из контекста: trace, auth, company, user, namespace):\n"
            "client = ServiceClient()\n"
            "await client.get(service, path, **kwargs)  # kwargs → httpx (params, json, timeout, headers, files, ...)\n"
            "await client.post(service, path, **kwargs)\n"
            "await client.request(service, method, path, timeout=30.0, **kwargs)\n"
            "service: crm, rag, flows, sync, frontend, ...; path — путь с ведущим /."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["http", "api", "platform"],
    },
    {
        "name": "ServiceClientError",
        "type": "exception",
        "doc": (
            "Ошибка вызова сервиса через ServiceClient:\n"
            "try:\n"
            "    data = await client.get('crm', '/crm/api/v1/entities/123')\n"
            "except ServiceClientError as e:\n"
            "    logger.error(f'Ошибка CRM: {e}')"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["http", "api", "platform"],
    },
    {
        "name": "get_mcp_client",
        "type": "function",
        "doc": (
            "Получить MCP-клиент по server_id из конфигурации компании:\n"
            "client = await get_mcp_client('browser', state=state, timeout=60.0)\n"
            "result = await client.call_tool('browser_observe', {'session_id': '...'})"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["mcp", "tools", "platform"],
    },
    {
        "name": "call_mcp_tool",
        "type": "function",
        "doc": (
            "Вызвать MCP tool без ручной сборки JSON-RPC:\n"
            "res = await call_mcp_tool('browser', 'browser_observe', {'session_id': '...'}, state=state)\n"
            "text = res.get_text(); content = res.content; is_error = res.is_error"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["mcp", "tools", "platform"],
    },
    {
        "name": "Search",
        "type": "class",
        "doc": (
            "Абстрактный контракт поиска URL по текстовому запросу.\n"
            "Метод: `async def links(self, state, query: str) -> list[str]`.\n"
            "Реализация по умолчанию для браузерного DuckDuckGo: `DuckDuckGoBrowserSearch`."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["mcp", "browser", "search"],
    },
    {
        "name": "Describe",
        "type": "class",
        "doc": (
            "Абстрактный контракт получения markdown страницы по HTTP(S) URL.\n"
            "Метод: `async def page_markdown(self, state, url: str) -> str`.\n"
            "Реализация через MCP browser и FileReader: `BrowserSnapshotDescribe`."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["mcp", "browser", "files"],
    },
    {
        "name": "DuckDuckGoBrowserSearch",
        "type": "class",
        "doc": (
            "`Search` через DuckDuckGo и MCP `browser` (как simple_crawler).\n"
            "`search = DuckDuckGoBrowserSearch()` или с параметрами `server_id`, `per_query_limit`, `blocked_hosts`.\n"
            "`urls = await search.links(state, 'запрос')`; несколько запросов: `await search.links_many(state, ['a','b'])`."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["mcp", "browser", "search"],
    },
    {
        "name": "BrowserSnapshotDescribe",
        "type": "class",
        "doc": (
            "`Describe`: сессия crawl, `browser_save_html_to_s3`, затем `FileReader.read` (как simple_crawler).\n"
            "`desc = BrowserSnapshotDescribe()`; опционально `navigation_timeout_ms`, `ingest_source`, `file_reader`.\n"
            "`text = await desc.page_markdown(state, 'https://example.com/path')`.\n"
            "`snap = await desc.page_snapshot(state, url)` — dict с ключами `url`, `file_id`, `s3_path`, `text`."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["mcp", "browser", "files"],
    },
    {
        "name": "browser_duckduckgo_links",
        "type": "FunctionTool",
        "doc": (
            "Тул ReAct: поиск ссылок через DuckDuckGo (`await tool.run(args, state)` или в `llm.chat(..., tools=[browser_duckduckgo_links])`).\n"
            "Аргументы: `query`, опционально `server_id`, `per_query_limit`.\n"
            "Ответ: `success`, при успехе `urls` — список HTTP(S) URL."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["mcp", "browser", "search", "web"],
    },
    {
        "name": "browser_duckduckgo_links_batch",
        "type": "FunctionTool",
        "doc": (
            "Тул ReAct: параллельный поиск по нескольким `queries`; ответ `urls` с дедупликацией.\n"
            "Опции `server_id`, `per_query_limit` — как у `browser_duckduckgo_links`."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["mcp", "browser", "search", "web"],
    },
    {
        "name": "browser_page_markdown",
        "type": "FunctionTool",
        "doc": (
            "Тул ReAct: markdown страницы по URL (MCP crawl + S3 + FileReader).\n"
            "Аргументы: `url`, опционально `server_id`, `navigation_timeout_ms`, `ingest_source`.\n"
            "Ответ: `success`, при успехе `markdown`."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["mcp", "browser", "web", "files"],
    },
    {
        "name": "browser_page_snapshot",
        "type": "FunctionTool",
        "doc": (
            "Тул ReAct: снимок страницы с идентификаторами файла.\n"
            "При успехе: `success`, `url`, `file_id`, `s3_path`, `text` (markdown)."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["mcp", "browser", "web", "files"],
    },
    {
        "name": "RagClient",
        "type": "class",
        "doc": (
            "Типизированный клиент RAG API (контекст компании в заголовках ServiceClient):\n"
            "client = RagClient()\n"
            "ns = await client.create_namespace('my_kb', 'описание')\n"
            "await client.ingest_text('my_kb', 'текст документа')\n"
            "hits = await client.search('my_kb', 'запрос', limit=5)"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["http", "rag", "api"],
    },
    {
        "name": "get_context",
        "type": "function",
        "doc": (
            "Контекст выполнения (company_id, user_id, namespace):\n"
            "ctx = get_context()\n"
            "company_id = ctx.active_company.company_id\n"
            "user_id = ctx.user.user_id\n"
            "namespace = ctx.active_namespace"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["context", "platform"],
    },
    {
        "name": "GoogleDocsClient",
        "type": "class",
        "doc": (
            "Клиент Google Docs API:\n"
            "client = GoogleDocsClient(credentials_json=..., access_token=..., subject=...)\n"
            "doc = await client.create_document('Title')\n"
            "text = await client.read_as_text(document_id)\n"
            "await client.append_text(document_id, 'text')\n"
            "await client.share_document(document_id, email, role='writer')\n\n"
            "Авторизация: SA JSON из variables, или access_token, или per-user OAuth через get_google_oauth_token."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["google", "docs", "api"],
    },
    {
        "name": "datetime",
        "type": "class",
        "doc": (
            "Класс datetime.datetime (не модуль целиком):\n"
            "now = datetime.now()\n"
            "dt = datetime.fromisoformat('2025-01-15T10:00:00')\n"
            "ts = datetime(2025, 6, 1, 12, 0)\n\n"
            "Для timedelta, date и т.д. используйте import datetime."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["datetime", "utility"],
    },
    # Фасады платформы
    {
        "name": "get_file_bytes",
        "type": "function",
        "doc": (
            "Скачать файл из хранилища по ID:\n"
            "raw = await get_file_bytes(file_id)\n"
            "# raw: bytes содержимого файла"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["files", "platform"],
    },
    {
        "name": "get_text_transform_service",
        "type": "callable",
        "doc": (
            "Фасад `platform_services.get_text_transform_service`: единый `TextTransformService` "
            "без `FlowContainer`.\n"
            "svc = get_text_transform_service()\n"
            "summary = await svc.summarize(text, max_output_tokens=..., provider=..., model=...)\n"
            "# model может быть `openrouter:vendor/model` или задайте provider+model отдельно.\n"
            "md = await svc.format_markdown(text, provider=None, model=None)\n"
            "# По умолчанию Markdown — HTTP `POST /v1/text/format_markdown` (LitServe); "
            "для openrouter/openai/… — чанкованный вызов `get_llm`.\n"
            "Биллинг: `require_balance` для LLM; для LitServe — span `llm.provider_litserve.format_markdown` "
            "и токены из ответа (`usage`)."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["text", "llm", "platform"],
    },
    {
        "name": "transcribe_audio",
        "type": "function",
        "doc": (
            "Распознать речь из persisted-аудио (`file_id` из `state.files`)\n"
            "и вернуть строку с текстом. Провайдер/модель/язык — через единый\n"
            "voice_resolver (override → company → deployment-default):\n"
            "text = await transcribe_audio(file_id, language='ru-RU')\n"
            "# или явный провайдер для этого вызова:\n"
            "text = await transcribe_audio(file_id, provider='cloud_ru', model='whisper-large-v3')\n"
            "# Списание STT: длительность через ffprobe; без неё usage не пишется.\n"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["voice", "stt", "files", "platform"],
    },
    {
        "name": "synthesize_speech",
        "type": "function",
        "doc": (
            "Синтез речи. Сохраняет результат в FileRepository + S3 и\n"
            "возвращает file_id сохранённого аудио (этот id агент кладёт в\n"
            "ответ или передаёт каналу). Провайдер/голос/язык — через единый\n"
            "voice_resolver (override → company → deployment-default):\n"
            "file_id = await synthesize_speech('Привет!', voice='alloy', language='ru-RU')\n"
            "file_id = await synthesize_speech('Hello', provider='litserve', model='silero-tts-v5-5-ru')"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["voice", "tts", "files", "platform"],
    },
    {
        "name": "get_google_oauth_token",
        "type": "function",
        "doc": (
            "Получить OAuth-токен Google для текущего пользователя:\n"
            "token = await get_google_oauth_token(state, service='docs')\n\n"
            "Если токена нет — бросает FlowInterrupt с OAuthInterrupt (flow встаёт на паузу, UI показывает кнопку авторизации)."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["google", "oauth", "platform"],
    },
    {
        "name": "get_schedule_service",
        "type": "function",
        "doc": (
            "Фасад планировщика задач:\n"
            "svc = get_schedule_service()\n"
            "task = await svc.schedule_cron_task(flow_id=..., session_id=..., ...)\n"
            "tasks = await svc.list_tasks(session_id=...)\n"
            "await svc.cancel_task(task_id)"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["scheduling", "platform"],
    },
    {
        "name": "get_oauth_service",
        "type": "function",
        "doc": (
            "Фасад OAuth-сервиса:\n"
            "svc = get_oauth_service()\n"
            "token = await svc.get_valid_token(company_id, user_id, 'google', 'docs')"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["oauth", "platform"],
    },
    {
        "name": "get_operator_handoff_service",
        "type": "function",
        "doc": (
            "Фасад операторских очередей:\n"
            "svc = get_operator_handoff_service()\n"
            "cid, task_id = await svc.register_handoff(state, question=..., task_title=..., assignee_queue_slug=..., handoff_mode=HandoffMode.single_reply)"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["operator", "hitl", "platform"],
    },
    {
        "name": "get_lara_facade",
        "type": "function",
        "doc": (
            "Фасад confirm-first операций Lara:\n"
            "facade = get_lara_facade()\n"
            "preview = await facade.preview_node_patch(flow_id=..., node_id=..., patch=..., branch_id='base', state=state, idempotency_key=None)\n"
            "applied = await facade.apply_node_patch(pending_action_id=..., state=state, idempotency_key=None)"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["lara", "assistant", "platform"],
    },
    {
        "name": "BaseTool",
        "type": "class",
        "doc": (
            "Базовый класс platform tools для объектов, которые передаются в `llm.chat(..., tools=[...])`. "
            "Не является точкой входа inline code / CodeNode: рантайм inline-кода вызывает только "
            "top-level функцию (`run`, `execute` или первую функцию в файле). Для обычного inline tool "
            "пиши функцию; для ad-hoc LLM-tools внутри кода обычно проще использовать `@tool`."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["tools", "llm"],
    },
    {
        "name": "quote",
        "type": "function",
        "doc": "URL-кодирование строки (urllib.parse.quote):\npath = f'/api/v1/items/{quote(item_id, safe=\"\")}'",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["url", "utility"],
    },
    {
        "name": "ContentType",
        "type": "enum",
        "doc": "Тип содержимого для планировщика:\nContentType('message') или ContentType('tool_call')",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["scheduling", "utility"],
    },
    # Файлы - классы
    {
        "name": "FileResponse",
        "type": "class",
        "doc": (
            "Модель ответа о файле:\n"
            "response = FileResponse.from_record(record)\n"
            "data = response.model_dump(mode='json')\n"
            "# -> {file_id, url, original_name, content_type, file_size, checksum, is_public}"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["files", "models"],
    },
    {
        "name": "DocxTemplater",
        "type": "class",
        "doc": (
            "Заполнение DOCX по Jinja2 (docxtpl):\n"
            "record = await DocxTemplater().fill_and_create(\n"
            "    file_ref=finfo,  # dict из state.files\n"
            "    context={'name': 'Иван'},\n"
            "    output_original_name='out.docx',\n"
            "    strict=False,\n"
            ")\n"
            "Без кода: tool fill_docx_template."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["files", "docx"],
    },
    {
        "name": "DocxTemplateError",
        "type": "exception",
        "doc": (
            "Ошибка шаблона DOCX (и подклассы DocxTemplateInvalidError, DocxTemplateSyntaxError и т.д.).\n"
            "У экземпляра: message, code, payload.\n"
            "В inline-коде запрещён доступ к атрибутам интроспекции из политики eval (например __class__, __bases__); "
            "super().__init__() и обычные методы классов — можно. Имя типа исключения: "
            "getattr(type(exc), \"__name__\", \"\"). Или вызывайте fill_docx_template."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["files", "docx", "exception"],
    },
    # JSON
    {
        "name": "extract_json",
        "type": "function",
        "doc": (
            "Извлечь JSON из текста, в том числе из fenced-блоков с меткой `json` в Markdown.\n\n"
            "`data = extract_json(llm_response)`\n\n"
            "Возвращает `dict` / `list` или `None`."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["json", "utility"],
    },
    # A2A типы
    {
        "name": "Message",
        "type": "class",
        "doc": (
            "A2A сообщение:\n"
            "import uuid\n"
            "msg = Message(messageId=str(uuid.uuid4()), role=Role.user, "
            "parts=[Part(root=TextPart(text='Привет'))], metadata={})"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["a2a", "types"],
    },
    {
        "name": "Part",
        "type": "class",
        "doc": "Контейнер для части сообщения:\nPart(root=TextPart(text='...')) или Part(root=DataPart(data={...}))",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["a2a", "types"],
    },
    {
        "name": "TextPart",
        "type": "class",
        "doc": "Текстовая часть сообщения:\nTextPart(text='Привет, мир!')",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["a2a", "types"],
    },
    {
        "name": "FilePart",
        "type": "class",
        "doc": (
            "Файловая часть:\n"
            "FilePart(file=FileWithBytes(name='doc.pdf', bytes=base64_str, mime_type='application/pdf'))\n"
            "Поле bytes — base64-строка, не сырые bytes."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["a2a", "types", "files"],
    },
    {
        "name": "DataPart",
        "type": "class",
        "doc": "Структурированные данные:\nDataPart(data={'result': 42, 'items': [1, 2, 3]})",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["a2a", "types"],
    },
    {
        "name": "Role",
        "type": "enum",
        "doc": "Роль в сообщении:\n- Role.user - сообщение пользователя\n- Role.agent - сообщение агента",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["a2a", "types"],
    },
    {
        "name": "Artifact",
        "type": "class",
        "doc": "Артефакт задачи:\nArtifact(artifactId='...', parts=[Part(...)])",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["a2a", "types"],
    },
    {
        "name": "httpx",
        "type": "module",
        "doc": (
            "HTTP клиент (обёртка httpx): get/post/put/patch/delete/request.\n"
            "Частые kwargs: params (query), json, data, content, files, headers, cookies, auth, "
            "timeout (число или httpx.Timeout), follow_redirects.\n"
            "Примеры: await httpx.get(url, params={'id': 1}, timeout=30.0); "
            "await httpx.post(url, json={'a': 1}, headers={'X-Key': 'v'}).\n"
            "Ответ: .status_code, .json(), .text, .headers"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["http", "api"],
    },
    {
        "name": "get_code_runner",
        "type": "callable",
        "doc": (
            "Фасад `platform_services.get_code_runner`: `get_code_runner(language=..., resources=...)` — "
            "`PythonCodeRunner` или runner для выбранного языка, без `FlowContainer` в namespace. "
            "В sandbox зарегистрирован для **паритета** `sandbox_codegen` (та же `exec`/`FunctionTool` строка). "
            "Полный DI в кастомном туле в БД — только через остальные фасады `platform_services` + `namespace`."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["eval", "codegen", "runtime"],
    },
    {
        "name": "get_llm",
        "type": "callable",
        "doc": (
            "Фабрика LLM (`core.clients.llm.get_llm`): `get_llm(model_name=..., state=...)`. Для мета-тула codegen в sandbox."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["eval", "codegen", "llm"],
    },
    {
        "name": "execution_state_for_codegen",
        "type": "callable",
        "doc": (
            "Копия `state` для прогона сгенерированного `async def run(state):` "
            "(`ExecutionState` или dict → валидированный `ExecutionState`, deep copy)."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["eval", "codegen"],
    },
    {
        "name": "run_codegen_stages",
        "type": "callable",
        "doc": (
            "Прогон сгенерированного кода песочницы: validate → compile → execute → проверка dict "
            "(`apps.flows.src.eval.codegen_utils`). Возвращает `CodegenStagesSuccess` / `CodegenStagesFailure`."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["eval", "codegen"],
    },
    {
        "name": "build_sandbox_docs_markdown",
        "type": "callable",
        "doc": "Async: Markdown документации API sandbox для промпта codegen (без каталога platform tools при `include_platform_tools=False`).",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["eval", "codegen", "docs"],
    },
    {
        "name": "CodegenStagesSuccess",
        "type": "class",
        "doc": "Результат успешного `run_codegen_stages`: поле `result: dict`.",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["eval", "codegen"],
    },
    {
        "name": "CodegenStagesFailure",
        "type": "class",
        "doc": "Ошибка стадии: `phase` (validate|compile|execute|result), `detail`, `traceback`.",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["eval", "codegen"],
    },
    {
        "name": "sandbox_feedback_hint",
        "type": "callable",
        "doc": "Эвристика подсказки LLM по тексту ошибки sandbox (импорты, интроспекция).",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["eval", "codegen"],
    },
    {
        "name": "syntax_retry_hint",
        "type": "callable",
        "doc": "Эвристика для retry при синтаксической ошибке и «склеенных» строках в сгенерированном коде.",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["eval", "codegen"],
    },
    {
        "name": "_system_rules_block",
        "type": "callable",
        "doc": "Текст системных правил промпта для мета-тула codegen (без вызова LLM).",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["eval", "codegen"],
    },
    {
        "name": "LLMGeneratedCode",
        "type": "class",
        "doc": "Pydantic-модель structured output: `code_lines: list[str]` — по одной физической строке .py на элемент.",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["eval", "codegen"],
    },
    {
        "name": "sandbox_codegen",
        "type": "tool",
        "doc": (
            "Мета-тул платформы: LLM генерирует inline Python по задаче, затем validate/compile/execute "
            "через `PythonCodeRunner` (оркестрация в `apps/flows/tools/sandbox_codegen.py`, механика прогона в "
            "`apps/flows/src/eval/codegen_utils.py`). Контракт кода: `async def run(state):` → dict; опционально "
            "`run_variables` сливается в `state.variables`. Ответ — JSON-строка с полями "
            "`success`, `result`, `final_code`, `attempts`, `trace`. В документации platform tools не перечисляется "
            "(`listed_in_platform_tool_docs=False`), чтобы не раздувать промпт мета-тула. "
            "Если тело тула копируют в редактор как отдельный фрагмент, значения по умолчанию в сигнатуре "
            "должны быть литералами или именами из whitelist sandbox — иначе при `exec` в песочнице будет NameError."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["eval", "codegen"],
    },
]
