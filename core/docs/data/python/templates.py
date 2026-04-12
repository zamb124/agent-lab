"""
Шаблоны кода для Python.
"""

from typing import Any, Dict, List

# Шаблоны для tool нод (execute function)
CODE_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "http_get",
        "name": "HTTP GET запрос",
        "description": "**Категория:** HTTP. `httpx.get` к внешнему URL; при ошибке статуса возвращает `{\"error\": ...}`.",
        "category": "http",
        "node_type": "tool",
        "tags": ["http", "api", "external"],
        "code": '''async def execute(url: str, state: dict = None):
    """
    HTTP GET запрос к внешнему API.
    
    Args:
        url: URL для запроса
        state: Текущее состояние
    
    Returns:
        JSON ответ от API
    """
    response = await httpx.get(url)
    
    if response.status_code != 200:
        return {"error": f"HTTP {response.status_code}"}
    
    return response.json()
''',
    },
    {
        "id": "http_post",
        "name": "HTTP POST запрос",
        "description": "**Категория:** HTTP. `httpx.post` с JSON-телом; ожидаемые статусы `200` / `201`.",
        "category": "http",
        "node_type": "tool",
        "tags": ["http", "api", "external"],
        "code": '''async def execute(url: str, data: dict = None, state: dict = None):
    """
    HTTP POST запрос к внешнему API.
    
    Args:
        url: URL для запроса
        data: Данные для отправки
        state: Текущее состояние
    
    Returns:
        JSON ответ от API
    """
    response = await httpx.post(url, json=data or {})
    
    if response.status_code not in (200, 201):
        return {"error": f"HTTP {response.status_code}"}
    
    return response.json()
''',
    },
    {
        "id": "llm_simple",
        "name": "LLM вызов",
        "description": "**Категория:** LLM. Один вызов `llm.chat(prompt)` и извлечение текста из первой части ответа.",
        "category": "llm",
        "node_type": "tool",
        "tags": ["llm", "ai"],
        "code": '''async def execute(prompt: str, state: dict = None):
    """
    Вызов LLM с промптом.
    
    Args:
        prompt: Текст запроса к LLM
        state: Текущее состояние
    
    Returns:
        Текстовый ответ от LLM
    """
    msg = await llm.chat(prompt)
    if not msg.parts:
        return ""
    part = msg.parts[0].root
    return getattr(part, "text", "") or ""
''',
    },
    {
        "id": "ask_user",
        "name": "Запрос у пользователя",
        "description": "**Категория:** interrupt. Вызывает `ask_user(question)` — выполнение останавливается до ответа пользователя.",
        "category": "interaction",
        "node_type": "tool",
        "tags": ["interrupt", "user", "interaction"],
        "code": '''async def execute(question: str = "Уточните, пожалуйста", state: dict = None):
    """
    Запрашивает информацию у пользователя.
    
    Args:
        question: Вопрос для пользователя
        state: Текущее состояние
    
    Returns:
        Ничего - выполнение прерывается
    """
    ask_user(question)
''',
    },
    {
        "id": "json_processing",
        "name": "Обработка JSON",
        "description": "**Категория:** данные. Использует `extract_json(text)` для разбора JSON из текста или MD-блоков.",
        "category": "data",
        "node_type": "tool",
        "tags": ["json", "parsing", "data"],
        "code": '''async def execute(text: str, state: dict = None):
    """
    Извлекает JSON из текста (включая markdown блоки).
    
    Args:
        text: Текст с JSON
        state: Текущее состояние
    
    Returns:
        Распарсенный JSON или ошибка
    """
    data = extract_json(text)
    
    if data is None:
        return {"error": "JSON не найден в тексте"}
    
    return data
''',
    },
    {
        "id": "file_processing",
        "name": "Обработка файлов",
        "description": "Чтение и обработка файлов из state",
        "category": "files",
        "node_type": "tool",
        "tags": ["files", "processing"],
        "code": '''async def execute(state: dict = None):
    """
    Обрабатывает файлы из state.
    
    Args:
        state: Текущее состояние с файлами
    
    Returns:
        Информация о файлах
    """
    files = get_files(state)
    
    if not files:
        return {"message": "Файлы не найдены"}
    
    results = []
    for file_info in files:
        res = await reader.read(file_info)
        preview = res.pages[0].text[:2000] if res.pages else ""
        results.append({
            "name": file_info["name"],
            "mime_type": file_info.get("mime_type", "unknown"),
            "detected_kind": str(res.detected_kind),
            "page_count": res.page_count,
            "text_preview": preview,
        })
    
    return {"files": results}
''',
    },
    {
        "id": "state_manipulation",
        "name": "Работа со state",
        "description": "Чтение и модификация state",
        "category": "state",
        "node_type": "tool",
        "tags": ["state", "data"],
        "code": '''async def execute(key: str, value: str = None, state: dict = None):
    """
    Читает или устанавливает значение в state.
    
    Args:
        key: Ключ (поддерживает путь через точку)
        value: Значение для установки (опционально)
        state: Текущее состояние
    
    Returns:
        Текущее или новое значение
    """
    if value is not None:
        set_nested(state, key, value)
        return {"key": key, "value": value, "action": "set"}
    
    current = get_nested(state, key)
    return {"key": key, "value": current, "action": "get"}
''',
    },
    {
        "id": "find_file_and_read",
        "name": "Поиск и чтение файла",
        "description": "**Категория:** файлы. Ищет файл по имени через `find_file`, затем читает через `reader`.",
        "category": "files",
        "node_type": "tool",
        "tags": ["files", "find_file", "reader"],
        "code": '''async def execute(file_name: str = None, state: dict = None):
    """
    Поиск файла по имени и извлечение текста.
    
    Args:
        file_name: Имя файла (подстрока); без имени — первый файл
        state: Текущее состояние
    
    Returns:
        Текст файла или ошибка
    """
    files = get_files(state)
    finfo = find_file(files, file_name)
    
    if not finfo:
        return {"error": f"Файл не найден: {file_name}"}
    
    res = await reader.read(finfo)
    text = "\\n".join(p.text for p in res.pages if p.text)
    
    return {
        "name": finfo["name"],
        "page_count": res.page_count,
        "text": text[:5000],
    }
''',
    },
    {
        "id": "llm_with_tools",
        "name": "LLM с tools (ReAct)",
        "description": "**Категория:** LLM. Вызов LLM с набором tools и ручной ReAct-цикл.",
        "category": "llm",
        "node_type": "tool",
        "tags": ["llm", "tools", "react"],
        "code": '''async def execute(prompt: str, state: dict = None):
    """
    LLM с tools: определяет tool_calls, выполняет и возвращает.
    
    Args:
        prompt: Промпт для LLM
        state: Текущее состояние
    """
    from a2a.utils.message import get_message_text

    @tool(name="calc", description="Вычислить выражение")
    def calc(expression: str):
        import ast
        return {"result": ast.literal_eval(expression)}

    msg = await llm.chat(prompt, tools=[calc])
    text = get_message_text(msg)
    
    if text:
        return {"response": text}

    tool_calls = (msg.metadata or {}).get("tool_calls", [])
    results = []
    for tc in tool_calls:
        if tc["function"]["name"] == "calc":
            args = json.loads(tc["function"]["arguments"])
            res = await calc.run(args, state)
            results.append(res)
    
    return {"tool_results": results}
''',
    },
    {
        "id": "service_client_call",
        "name": "Вызов сервиса платформы",
        "description": "**Категория:** HTTP. Запрос к другому сервису через `ServiceClient`.",
        "category": "http",
        "node_type": "tool",
        "tags": ["http", "api", "platform"],
        "code": '''async def execute(query: str, state: dict = None):
    """
    Поиск сущностей через CRM API.
    
    Args:
        query: Поисковый запрос
        state: Текущее состояние
    """
    client = ServiceClient()
    data = await client.post(
        "crm",
        "/crm/api/v1/entities/search",
        json={"query": query, "limit": 10},
    )
    return {"entities": data.get("items", [])}
''',
    },
]

# Шаблоны для function нод (run function)
FUNCTION_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "fn_http_get",
        "name": "HTTP GET запрос",
        "description": "Запрос к API и сохранение результата в state",
        "category": "http",
        "node_type": "function",
        "tags": ["http", "api", "external"],
        "code": '''async def run(state):
    """HTTP GET запрос к API."""
    url = state.get("api_url", "https://api.example.com/data")
    
    response = await httpx.get(url)
    
    if response.status_code == 200:
        state["api_response"] = response.json()
    else:
        state["api_error"] = f"HTTP {response.status_code}"
    
    return state
''',
    },
    {
        "id": "fn_http_post",
        "name": "HTTP POST запрос",
        "description": "Отправка данных на API",
        "category": "http",
        "node_type": "function",
        "tags": ["http", "api", "external"],
        "code": '''async def run(state):
    """HTTP POST запрос к API."""
    url = state.get("api_url", "https://api.example.com/data")
    data = state.get("post_data", {})
    
    response = await httpx.post(url, json=data)
    
    if response.status_code in (200, 201):
        state["api_response"] = response.json()
    else:
        state["api_error"] = f"HTTP {response.status_code}"
    
    return state
''',
    },
    {
        "id": "fn_llm_call",
        "name": "LLM вызов",
        "description": "Вызов LLM и сохранение ответа в state",
        "category": "llm",
        "node_type": "function",
        "tags": ["llm", "ai"],
        "code": '''async def run(state):
    """Вызов LLM с контекстом из state."""
    content = state.get("content", "")
    
    prompt = f"Обработай следующий запрос: {content}"
    msg = await llm.chat(prompt)
    text = ""
    if msg.parts:
        part = msg.parts[0].root
        text = getattr(part, "text", "") or ""
    state["response"] = text
    return state
''',
    },
    {
        "id": "fn_classifier",
        "name": "Классификатор",
        "description": "Классификация входного текста через LLM",
        "category": "llm",
        "node_type": "function",
        "tags": ["llm", "ai", "classification"],
        "code": '''async def run(state):
    """Классификация текста через LLM."""
    content = state.get("content", "")
    
    prompt = f"""Классифицируй запрос пользователя.
Категории: question, complaint, request, greeting, other

Запрос: {content}

Ответь одним словом - категорией."""
    
    msg = await llm.chat(prompt)
    raw = ""
    if msg.parts:
        part = msg.parts[0].root
        raw = getattr(part, "text", "") or ""
    state["category"] = raw.strip().lower()
    
    return state
''',
    },
    {
        "id": "fn_ask_user",
        "name": "Запрос у пользователя",
        "description": "Прерывание для запроса информации",
        "category": "interaction",
        "node_type": "function",
        "tags": ["interrupt", "user", "interaction"],
        "code": '''async def run(state):
    """Запрос дополнительной информации у пользователя."""
    if not state.get("user_email"):
        ask_user("Пожалуйста, укажите ваш email")
    
    state["email_confirmed"] = True
    return state
''',
    },
    {
        "id": "fn_json_extract",
        "name": "Извлечение JSON",
        "description": "Извлечение JSON из текста в state",
        "category": "data",
        "node_type": "function",
        "tags": ["json", "parsing", "data"],
        "code": '''async def run(state):
    """Извлечение JSON из текста."""
    text = state.get("raw_text", "")
    
    data = extract_json(text)
    
    if data:
        state["extracted_data"] = data
    else:
        state["extraction_error"] = "JSON не найден"
    
    return state
''',
    },
    {
        "id": "fn_file_process",
        "name": "Обработка файлов",
        "description": "Чтение файлов из state",
        "category": "files",
        "node_type": "function",
        "tags": ["files", "processing"],
        "code": '''async def run(state):
    """Обработка прикрепленных файлов."""
    files = get_files(state)
    
    if not files:
        state["response"] = "Файлы не найдены"
        return state
    
    results = []
    for file_info in files:
        res = await reader.read(file_info)
        preview = res.pages[0].text[:2000] if res.pages else ""
        results.append({
            "name": file_info["name"],
            "detected_kind": str(res.detected_kind),
            "page_count": res.page_count,
            "text_preview": preview,
        })
    
    state["files_info"] = results
    return state
''',
    },
    {
        "id": "fn_conditional",
        "name": "Условная логика",
        "description": "Условный переход в зависимости от state",
        "category": "logic",
        "node_type": "function",
        "tags": ["logic", "conditional", "routing"],
        "code": '''async def run(state):
    """Условная логика с разными путями."""
    category = state.get("category", "other")
    
    if category == "complaint":
        state["response"] = "Передаю вашу жалобу специалисту..."
        state["next_node"] = "complaint_handler"
    elif category == "question":
        state["response"] = "Ищу ответ на ваш вопрос..."
        state["next_node"] = "faq_search"
    else:
        state["response"] = "Чем могу помочь?"
        state["next_node"] = "default_handler"
    
    return state
''',
    },
    {
        "id": "fn_set_response",
        "name": "Установка ответа",
        "description": "Простая установка response в state",
        "category": "basic",
        "node_type": "function",
        "tags": ["basic", "response"],
        "code": '''async def run(state):
    """Установка ответа пользователю."""
    content = state.get("content", "")
    
    state["response"] = f"Вы написали: {content}"
    
    return state
''',
    },
    {
        "id": "fn_find_and_process_file",
        "name": "Поиск и обработка файла",
        "description": "Поиск файла через find_file и чтение содержимого",
        "category": "files",
        "node_type": "function",
        "tags": ["files", "find_file", "reader"],
        "code": '''async def run(state):
    """Найти файл по имени и прочитать."""
    file_name = state.get("target_file")
    files = get_files(state)
    finfo = find_file(files, file_name)
    
    if not finfo:
        state["response"] = f"Файл {file_name!r} не найден"
        return state
    
    res = await reader.read(finfo)
    state["file_text"] = "\\n".join(p.text for p in res.pages if p.text)
    state["file_name"] = finfo["name"]
    
    return state
''',
    },
    {
        "id": "fn_llm_with_tools",
        "name": "LLM с tools",
        "description": "Вызов LLM с определёнными tools в ноде",
        "category": "llm",
        "node_type": "function",
        "tags": ["llm", "tools", "react"],
        "code": '''async def run(state):
    """LLM с tools внутри code_node."""
    from a2a.utils.message import get_message_text

    @tool(name="lookup", description="Поиск по базе знаний")
    def lookup(query: str):
        client = ServiceClient()
        return {"answer": "Результат поиска"}

    content = state.get("content", "")
    msg = await llm.chat(content, tools=[lookup, ask_user_tool])
    state["response"] = get_message_text(msg) or ""
    
    return state
''',
    },
    {
        "id": "fn_interrupt_flow",
        "name": "Прерывание flow (FlowInterrupt)",
        "description": "Запрос данных у пользователя с FlowInterrupt",
        "category": "interaction",
        "node_type": "function",
        "tags": ["interrupt", "flow"],
        "code": '''async def run(state):
    """Запрос недостающих данных через FlowInterrupt."""
    if not state.get("city"):
        ask_user("В каком городе вы находитесь?")
    
    if not state.get("phone"):
        raise FlowInterrupt(question="Укажите ваш номер телефона")
    
    state["profile_complete"] = True
    return state
''',
    },
]
