"""
Глобальные переменные для Python inline кода.
"""

from typing import Any, Dict, List

# Глобальные переменные с поддержкой perspectives
GLOBALS: List[Dict[str, Any]] = [
    # State - главная сущность
    {
        "name": "state",
        "type": "Dict[str, Any]",
        "doc": (
            "Главный объект данных (передаётся в run(state)):\n"
            "- state['content'] - текст последнего сообщения пользователя\n"
            "- state['response'] - ответ для пользователя (установите)\n"
            "- state['messages'] - история сообщений List[Message]\n"
            "- state['files'] - файлы [{name, path, mime_type}]\n"
            "- state['user_id'] - ID пользователя\n"
            "- state['user_groups'] - группы пользователя\n"
            "- state['variables'] - переменные агента\n"
            "- state['current_nodes'] - текущие ноды\n"
            "- state['custom_key'] - любые ваши данные"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["core", "data"],
    },
    # LLM клиент
    {
        "name": "llm",
        "type": "SafeLLMClient",
        "doc": (
            "LLM клиент для вызова моделей. Использование:\n"
            "- await llm.chat_simple('Привет!') -> str\n"
            "- await llm.chat(messages) -> Message\n"
            "- await llm.chat_with_tools(messages, tools) -> Message"
        ),
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["llm", "ai"],
    },
    # Контекст и канал
    {
        "name": "context",
        "type": "SafeContext",
        "doc": (
            "Контекст выполнения (только чтение):\n"
            "- context.channel - канал (a2a, telegram, api)\n"
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
        "doc": "Установить вложенное значение по пути:\nstate = set_nested(state, 'user.name', 'Иван')",
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
        "name": "get_user",
        "type": "function",
        "doc": "Получить информацию о пользователе:\nuser = get_user(state)\n# -> {id, email, grps}",
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
        "doc": "Запросить информацию у пользователя:\nask_user('Как вас зовут?')\n# Прерывает выполнение и ждёт ответа",
        "perspectives": ["editor", "flow", "tool", "node"],
        "tags": ["interrupt", "interaction"],
    },
    # JSON
    {
        "name": "extract_json",
        "type": "function",
        "doc": "Извлечь JSON из текста (поддерживает ```json``` блоки):\ndata = extract_json(llm_response)\n# -> dict/list или None",
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
        "doc": "Файловая часть сообщения:\nFilePart(file=FileWithBytes(name='doc.pdf', bytes=data))",
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
