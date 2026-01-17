"""
Шаблоны кода для Python.
"""

from typing import Any, Dict, List

# Шаблоны для tool нод (execute function)
CODE_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "http_get",
        "name": "HTTP GET запрос",
        "description": "Запрос к внешнему API с обработкой ответа",
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
        "description": "Отправка данных на внешний API",
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
        "description": "Простой вызов LLM с промптом",
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
    response = await llm.chat_simple(prompt)
    return response
''',
    },
    {
        "id": "ask_user",
        "name": "Запрос у пользователя",
        "description": "Прерывание выполнения для запроса информации у пользователя",
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
        "description": "Извлечение и обработка JSON из текста",
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
        content = read_file(file_info["path"])
        results.append({
            "name": file_info["name"],
            "size": len(content),
            "mime_type": file_info.get("mime_type", "unknown"),
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
    response = await llm.chat_simple(prompt)
    
    state["response"] = response
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
    
    category = await llm.chat_simple(prompt)
    state["category"] = category.strip().lower()
    
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
        content = read_file(file_info["path"])
        results.append({
            "name": file_info["name"],
            "size": len(content),
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
]
