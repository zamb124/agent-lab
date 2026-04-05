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
            "- **`task_id`**, **`context_id`**, **`user_id`**, **`session_id`** — обязательные системные поля\n"
            "- **`content`** — вход пользователя; **`response`** — ответ агента; **`result`** — результат ноды/tool\n"
            "- **`messages`** — `List[Message]`; **`files`** — список вложений `{name, path, mime_type, ...}`\n"
            "- **`user_groups`**, **`variables`**, **`current_nodes`** — группы, переменные flow, активные ноды\n"
            "- дополнительные поля через присваивание; сериализация: `state.model_dump()`"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["core", "data"],
    },
    # LLM клиент
    {
        "name": "llm",
        "type": "SafeLLMClient",
        "doc": (
            "await llm.chat(messages, *ключевые_аргументы). Первый аргумент messages:\n"
            "str | list[str] | Message | list[Message] | dict | list[dict] (роли/контент нормализуются рантаймом).\n"
            "Возврат: Message (текст, tool_calls в metadata) или экземпляр response_model при structured output.\n"
            "Ключевые параметры (все опциональны, кроме смысла вызова):\n"
            "- model — имя модели; response_model — Pydantic-модель для JSON по схеме\n"
            "- tools — список: готовые OpenAI dict ИЛИ результат @tool(...) (имя функции после декоратора — экземпляр tool с to_openai_schema); сырую функцию без @tool передавать нельзя\n"
            "- temperature, top_p, top_k, max_tokens, frequency_penalty, presence_penalty — семплинг и лимиты\n"
            "- seed — детерминизм (если провайдер поддерживает); reasoning_effort — строка для reasoning API\n"
            "- extra_body — dict: произвольные поля тела HTTP-запроса к провайдеру; мержатся последними и перекрывают совпадения\n"
            "Текст ответа удобно брать: from a2a.utils.message import get_message_text\nget_message_text(msg)"
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
            "reason, final_answer, finish, self_check, задачи планировщика (schedule_*), … "
            "Новый системный tool подключается разработчиками платформы в реестр пакета tools."
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["tools", "platform"],
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
        "doc": "A2A сообщение:\nmsg = Message(messageId=str(uuid4()), role=Role.user, parts=[Part(root=TextPart(text='Привет'))])",
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
            "HTTP клиент для внешних API (точно как httpx):\n"
            "- response = await httpx.get(url, params={...})\n"
            "- response = await httpx.post(url, json={...})\n"
            "- response = await httpx.put(url, json={...})\n"
            "- response = await httpx.patch(url, json={...})\n"
            "- response = await httpx.delete(url)\n"
            "- response = await httpx.request(method, url, ...)\n"
            "- response.json() - получить JSON ответ\n"
            "- response.text - получить текст ответа\n"
            "- response.status_code - код статуса\n"
            "- response.headers - заголовки ответа"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["http", "api"],
    },
]
