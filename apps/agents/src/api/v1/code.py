"""
API endpoints для работы с кодом.
Предоставляет данные для autocomplete в редакторе Python.
Эндпоинты для валидации и выполнения inline кода.
"""

import builtins
import copy
import importlib
import inspect
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.logging import get_logger
from apps.agents.src.agent.nodes import create_node
from apps.agents.src.api.v1.agents import _inline_tools_list
from apps.agents.src.container import get_container
from apps.agents.src.eval.safe_eval import (
    BLOCKED_BUILTINS,
    SafeEvalError,
    _validate_code,
    compile_function,
    safe_eval,
)
import uuid
from core.state import ExecutionState

router = APIRouter(tags=["code"])
logger = get_logger(__name__)


class GlobalVariable(BaseModel):
    """Глобальная переменная доступная в inline коде"""
    name: str
    type: str
    doc: str


class StateField(BaseModel):
    """Поле ExecutionState"""
    name: str
    type: str
    description: str
    readonly: bool = False


class CodeTemplate(BaseModel):
    """Шаблон кода"""
    id: str
    name: str
    description: str
    code: str
    category: str


class CodeCompletionsResponse(BaseModel):
    """Данные для autocomplete в редакторе кода"""
    modules: List[str]
    globals: List[GlobalVariable]
    builtins: List[str]
    module_methods: Dict[str, List[Dict[str, Any]]]
    state_fields: List[StateField] = []
    templates: List[CodeTemplate] = []


MODULE_METHODS: Dict[str, List[Dict[str, Any]]] = {
    "json": [
        {"name": "dumps", "type": "function", "doc": "Сериализует объект в JSON строку: json.dumps(obj, indent=2)"},
        {"name": "loads", "type": "function", "doc": "Парсит JSON строку в объект: json.loads(json_string)"},
        {"name": "dump", "type": "function", "doc": "Записывает объект в JSON файл"},
        {"name": "load", "type": "function", "doc": "Читает объект из JSON файла"},
    ],
    "re": [
        {"name": "match", "type": "function", "doc": "Проверка совпадения в начале строки: re.match(r'pattern', text)"},
        {"name": "search", "type": "function", "doc": "Поиск паттерна в строке: re.search(r'pattern', text)"},
        {"name": "findall", "type": "function", "doc": "Найти все совпадения: re.findall(r'\\d+', text) -> ['1', '2']"},
        {"name": "sub", "type": "function", "doc": "Замена по паттерну: re.sub(r'old', 'new', text)"},
        {"name": "split", "type": "function", "doc": "Разделить по паттерну: re.split(r'[,;]', text)"},
        {"name": "compile", "type": "function", "doc": "Скомпилировать паттерн для многократного использования"},
    ],
    "datetime": [
        {"name": "datetime", "type": "class", "doc": "Дата и время: datetime.now(), datetime.fromisoformat('2024-01-01')"},
        {"name": "date", "type": "class", "doc": "Только дата: date.today(), date(2024, 1, 1)"},
        {"name": "time", "type": "class", "doc": "Только время: time(12, 30, 0)"},
        {"name": "timedelta", "type": "class", "doc": "Разница времени: timedelta(days=1, hours=2)"},
    ],
    "math": [
        {"name": "sqrt", "type": "function", "doc": "Квадратный корень: math.sqrt(16) -> 4.0"},
        {"name": "ceil", "type": "function", "doc": "Округление вверх: math.ceil(1.2) -> 2"},
        {"name": "floor", "type": "function", "doc": "Округление вниз: math.floor(1.8) -> 1"},
        {"name": "pow", "type": "function", "doc": "Степень: math.pow(2, 3) -> 8.0"},
        {"name": "log", "type": "function", "doc": "Натуральный логарифм: math.log(10)"},
        {"name": "sin", "type": "function", "doc": "Синус в радианах: math.sin(math.pi/2)"},
        {"name": "cos", "type": "function", "doc": "Косинус в радианах: math.cos(0) -> 1.0"},
        {"name": "pi", "type": "constant", "doc": "Число Пи: 3.141592653589793"},
    ],
    "random": [
        {"name": "random", "type": "function", "doc": "Случайное float от 0 до 1: random.random()"},
        {"name": "randint", "type": "function", "doc": "Случайное целое: random.randint(1, 100)"},
        {"name": "choice", "type": "function", "doc": "Случайный выбор: random.choice(['a', 'b', 'c'])"},
        {"name": "shuffle", "type": "function", "doc": "Перемешать список: random.shuffle(items)"},
        {"name": "sample", "type": "function", "doc": "Случайная выборка: random.sample(items, k=3)"},
    ],
    "uuid": [
        {"name": "uuid4", "type": "function", "doc": "Сгенерировать случайный UUID: str(uuid.uuid4())"},
        {"name": "UUID", "type": "class", "doc": "Класс UUID для работы с идентификаторами"},
    ],
    "base64": [
        {"name": "b64encode", "type": "function", "doc": "Кодировать в base64: base64.b64encode(b'data').decode()"},
        {"name": "b64decode", "type": "function", "doc": "Декодировать из base64: base64.b64decode(encoded)"},
    ],
    "hashlib": [
        {"name": "md5", "type": "function", "doc": "MD5 хеш: hashlib.md5(b'text').hexdigest()"},
        {"name": "sha256", "type": "function", "doc": "SHA-256 хеш: hashlib.sha256(b'text').hexdigest()"},
        {"name": "sha1", "type": "function", "doc": "SHA-1 хеш: hashlib.sha1(b'text').hexdigest()"},
    ],
    "collections": [
        {"name": "Counter", "type": "class", "doc": "Подсчет элементов: Counter(['a', 'b', 'a']) -> {'a': 2, 'b': 1}"},
        {"name": "defaultdict", "type": "class", "doc": "Dict с значением по умолчанию: defaultdict(list)"},
        {"name": "OrderedDict", "type": "class", "doc": "Упорядоченный словарь (сохраняет порядок ключей)"},
        {"name": "namedtuple", "type": "function", "doc": "Именованный кортеж: Point = namedtuple('Point', ['x', 'y'])"},
    ],
    "itertools": [
        {"name": "chain", "type": "function", "doc": "Объединить итераторы: chain([1, 2], [3, 4]) -> [1, 2, 3, 4]"},
        {"name": "cycle", "type": "function", "doc": "Бесконечный цикл: cycle([1, 2, 3]) -> 1, 2, 3, 1, 2, 3..."},
        {"name": "repeat", "type": "function", "doc": "Повторить значение: repeat('x', 3) -> 'x', 'x', 'x'"},
        {"name": "zip_longest", "type": "function", "doc": "Zip с заполнением: zip_longest([1,2], [3], fillvalue=0)"},
        {"name": "groupby", "type": "function", "doc": "Группировка: groupby(sorted(items), key=lambda x: x[0])"},
    ],
    "functools": [
        {"name": "reduce", "type": "function", "doc": "Свёртка списка: reduce(lambda a,b: a+b, [1,2,3]) -> 6"},
        {"name": "partial", "type": "function", "doc": "Частичное применение: partial(func, arg1=value)"},
        {"name": "lru_cache", "type": "function", "doc": "Кеширование: @lru_cache(maxsize=128)"},
    ],
    "pydantic": [
        {"name": "BaseModel", "type": "class", "doc": "Базовый класс модели с валидацией: class User(BaseModel): name: str"},
        {"name": "Field", "type": "function", "doc": "Поле с метаданными: name: str = Field(..., min_length=1)"},
        {"name": "validator", "type": "decorator", "doc": "Валидатор поля: @validator('email')"},
        {"name": "root_validator", "type": "decorator", "doc": "Валидатор всей модели: @root_validator"},
    ],
    "a2a.types": [
        {"name": "Message", "type": "class", "doc": "A2A сообщение: Message(messageId, role, parts, metadata)"},
        {"name": "Part", "type": "class", "doc": "Часть сообщения: Part(root=TextPart(text='...'))"},
        {"name": "TextPart", "type": "class", "doc": "Текстовая часть: TextPart(text='Привет')"},
        {"name": "FilePart", "type": "class", "doc": "Файловая часть: FilePart(file=FileWithBytes(...))"},
        {"name": "DataPart", "type": "class", "doc": "Структурированные данные: DataPart(data={'key': 'value'})"},
        {"name": "Role", "type": "enum", "doc": "Роль сообщения: Role.user или Role.agent"},
        {"name": "Artifact", "type": "class", "doc": "Артефакт задачи: Artifact(artifactId, parts)"},
        {"name": "Task", "type": "class", "doc": "A2A задача со статусом и историей"},
        {"name": "TaskState", "type": "enum", "doc": "Статус задачи: submitted, working, completed, failed"},
        {"name": "TaskStatus", "type": "class", "doc": "Статус с состоянием и сообщением"},
    ],
    "httpx": [
        {"name": "get", "type": "function", "doc": "GET запрос: response = await httpx.get('https://api.example.com/data', params={'id': 1}); data = response.json()"},
        {"name": "post", "type": "function", "doc": "POST запрос: response = await httpx.post('https://api.example.com/data', json={'name': 'test'})"},
        {"name": "put", "type": "function", "doc": "PUT запрос: response = await httpx.put('https://api.example.com/data/1', json={'name': 'updated'})"},
        {"name": "patch", "type": "function", "doc": "PATCH запрос: response = await httpx.patch('https://api.example.com/data/1', json={'name': 'patched'})"},
        {"name": "delete", "type": "function", "doc": "DELETE запрос: response = await httpx.delete('https://api.example.com/data/1')"},
        {"name": "request", "type": "function", "doc": "Универсальный запрос: response = await httpx.request('POST', url, json={...})"},
    ],
    "llm": [
        {"name": "chat_simple", "type": "function", "doc": "Простой вызов LLM: text = await llm.chat_simple('Привет!')"},
        {"name": "chat", "type": "function", "doc": "Вызов LLM с Message: msg = await llm.chat(messages)"},
        {"name": "chat_with_tools", "type": "function", "doc": "Вызов LLM с tools: msg = await llm.chat_with_tools(messages, tools)"},
    ],
    "context": [
        {"name": "channel", "type": "property", "doc": "Канал коммуникации: 'a2a', 'telegram', 'api'"},
        {"name": "user_id", "type": "property", "doc": "ID пользователя"},
        {"name": "session_id", "type": "property", "doc": "ID сессии"},
        {"name": "agent_id", "type": "property", "doc": "ID агента"},
        {"name": "metadata", "type": "property", "doc": "Метаданные запроса (dict)"},
    ],
    "channel": [
        {"name": "send", "type": "function", "doc": "Отправить сообщение: await channel.send('Текст')"},
        {"name": "send_with_buttons", "type": "function", "doc": "С кнопками: await channel.send_with_buttons('Выберите:', ['Да', 'Нет'])"},
    ],
    "logger": [
        {"name": "info", "type": "function", "doc": "Информация: logger.info('Сообщение')"},
        {"name": "warning", "type": "function", "doc": "Предупреждение: logger.warning('Внимание!')"},
        {"name": "error", "type": "function", "doc": "Ошибка: logger.error('Ошибка', exc_info=True)"},
        {"name": "debug", "type": "function", "doc": "Отладка: logger.debug('Debug info')"},
    ],
    "state": [
        {"name": "get", "type": "function", "doc": "Получить значение: state.get('key', default)"},
        {"name": "keys", "type": "function", "doc": "Список ключей: state.keys()"},
        {"name": "values", "type": "function", "doc": "Список значений: state.values()"},
        {"name": "items", "type": "function", "doc": "Пары ключ-значение: state.items()"},
        {"name": "update", "type": "function", "doc": "Обновить: state.update({'key': 'value'})"},
    ],
}

STATE_FIELDS: List[Dict[str, Any]] = [
    {"name": "content", "type": "str", "description": "Текст последнего сообщения пользователя", "readonly": False},
    {"name": "response", "type": "str", "description": "Ответ для пользователя (установите)", "readonly": False},
    {"name": "messages", "type": "List[Message]", "description": "История сообщений", "readonly": False},
    {"name": "files", "type": "List[dict]", "description": "Файлы [{name, path, mime_type, size}]", "readonly": True},
    {"name": "user_id", "type": "str", "description": "ID пользователя", "readonly": True},
    {"name": "user_groups", "type": "List[str]", "description": "Группы пользователя", "readonly": True},
    {"name": "variables", "type": "dict", "description": "Переменные агента", "readonly": True},
    {"name": "current_nodes", "type": "List[str]", "description": "Текущие ноды для выполнения", "readonly": True},
    {"name": "task_id", "type": "str", "description": "ID задачи", "readonly": True},
    {"name": "context_id", "type": "str", "description": "ID контекста", "readonly": True},
    {"name": "session_id", "type": "str", "description": "ID сессии", "readonly": True},
    {"name": "tool_results", "type": "dict", "description": "Результаты выполненных tools", "readonly": True},
]

CODE_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "http_get",
        "name": "HTTP GET запрос",
        "description": "Запрос к внешнему API с обработкой ответа",
        "category": "http",
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

FUNCTION_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "fn_http_get",
        "name": "HTTP GET запрос",
        "description": "Запрос к API и сохранение результата в state",
        "category": "http",
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
        "code": '''async def run(state):
    """Запрос дополнительной информации у пользователя."""
    # Проверяем, есть ли нужные данные
    if not state.get("user_email"):
        ask_user("Пожалуйста, укажите ваш email")
    
    # Код продолжится после ответа пользователя
    state["email_confirmed"] = True
    return state
''',
    },
    {
        "id": "fn_json_extract",
        "name": "Извлечение JSON",
        "description": "Извлечение JSON из текста в state",
        "category": "data",
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
        "code": '''async def run(state):
    """Установка ответа пользователю."""
    content = state.get("content", "")
    
    # Ваша логика обработки
    state["response"] = f"Вы написали: {content}"
    
    return state
''',
    },
]


@router.get("/completions", response_model=CodeCompletionsResponse)
async def get_code_completions() -> CodeCompletionsResponse:
    """
    Возвращает данные для autocomplete в Python редакторе.
    
    - modules: доступные модули для import
    - globals: глобальные переменные (llm, context, etc.)
    - builtins: встроенные функции Python
    """
    globals_list = [
        # State - главная сущность
        GlobalVariable(
            name="state",
            type="Dict[str, Any]",
            doc="Главный объект данных (передаётся в run(state)):\n"
                "• state['content'] - текст последнего сообщения пользователя\n"
                "• state['response'] - ответ для пользователя (установите)\n"
                "• state['messages'] - история сообщений List[Message]\n"
                "• state['files'] - файлы [{name, path, mime_type}]\n"
                "• state['user_id'] - ID пользователя\n"
                "• state['user_groups'] - группы пользователя\n"
                "• state['variables'] - переменные агента\n"
                "• state['current_nodes'] - текущие ноды\n"
                "• state['custom_key'] - любые ваши данные"
        ),
        # LLM клиент
        GlobalVariable(
            name="llm",
            type="SafeLLMClient",
            doc="LLM клиент для вызова моделей. Использование:\n"
                "• await llm.chat_simple('Привет!') -> str\n"
                "• await llm.chat(messages) -> Message\n"
                "• await llm.chat_with_tools(messages, tools) -> Message"
        ),
        # Контекст и канал
        GlobalVariable(
            name="context",
            type="SafeContext",
            doc="Контекст выполнения (только чтение):\n"
                "• context.channel - канал (a2a, telegram, api)\n"
                "• context.user_id - ID пользователя\n"
                "• context.session_id - ID сессии\n"
                "• context.agent_id - ID агента\n"
                "• context.metadata - dict с метаданными"
        ),
        GlobalVariable(
            name="channel",
            type="SafeChannel",
            doc="Канал для отправки сообщений пользователю:\n"
                "• await channel.send('Текст сообщения')\n"
                "• await channel.send_with_buttons('Выберите:', ['Да', 'Нет'])"
        ),
        GlobalVariable(
            name="variables",
            type="dict",
            doc="Переменные агента (только для чтения). Доступ: variables['key'] или variables.get('key', default)"
        ),
        GlobalVariable(
            name="logger",
            type="Logger",
            doc="Логгер для отладки:\n"
                "• logger.info('Сообщение')\n"
                "• logger.warning('Предупреждение')\n"
                "• logger.error('Ошибка', exc_info=True)"
        ),
        # State утилиты (базовые)
        GlobalVariable(
            name="deep_copy_state",
            type="function",
            doc="Глубокое копирование state:\n"
                "copy = deep_copy_state(state)"
        ),
        GlobalVariable(
            name="merge_state",
            type="function",
            doc="Объединение двух state (глубокий merge):\n"
                "result = merge_state(base_state, updates)"
        ),
        GlobalVariable(
            name="get_nested",
            type="function",
            doc="Получить вложенное значение по пути:\n"
                "• get_nested(state, 'user.profile.name')\n"
                "• get_nested(state, 'data.items', default=[])"
        ),
        GlobalVariable(
            name="set_nested",
            type="function",
            doc="Установить вложенное значение по пути:\n"
                "state = set_nested(state, 'user.name', 'Иван')"
        ),
        # State утилиты (расширенные)
        GlobalVariable(
            name="get_files",
            type="function",
            doc="Получить файлы из state:\n"
                "files = get_files(state)\n"
                "# -> [{name, path, mime_type, size}, ...]"
        ),
        GlobalVariable(
            name="get_user",
            type="function",
            doc="Получить информацию о пользователе:\n"
                "user = get_user(state)\n"
                "# -> {id, email, grps}"
        ),
        GlobalVariable(
            name="get_tool_result",
            type="function",
            doc="Получить результат выполнения tool:\n"
                "result = get_tool_result(state, 'calculator')"
        ),
        GlobalVariable(
            name="get_messages",
            type="function",
            doc="Получить историю сообщений:\n"
                "messages = get_messages(state)\n"
                "# -> List[Message]"
        ),
        GlobalVariable(
            name="add_user_message",
            type="function",
            doc="Добавить сообщение пользователя в историю:\n"
                "state = add_user_message(state, 'Текст')"
        ),
        GlobalVariable(
            name="add_agent_message",
            type="function",
            doc="Добавить сообщение агента в историю:\n"
                "state = add_agent_message(state, 'Ответ агента')"
        ),
        # Interrupt
        GlobalVariable(
            name="ask_user",
            type="function",
            doc="Запросить информацию у пользователя:\n"
                "ask_user('Как вас зовут?')\n"
                "# Прерывает выполнение и ждёт ответа"
        ),
        # JSON
        GlobalVariable(
            name="extract_json",
            type="function",
            doc="Извлечь JSON из текста (поддерживает ```json``` блоки):\n"
                "data = extract_json(llm_response)\n"
                "# -> dict/list или None"
        ),
        # A2A типы
        GlobalVariable(
            name="Message",
            type="class",
            doc="A2A сообщение:\n"
                "msg = Message(messageId=str(uuid4()), role=Role.user, parts=[Part(root=TextPart(text='Привет'))])"
        ),
        GlobalVariable(
            name="Part",
            type="class",
            doc="Контейнер для части сообщения:\n"
                "Part(root=TextPart(text='...')) или Part(root=DataPart(data={...}))"
        ),
        GlobalVariable(
            name="TextPart",
            type="class",
            doc="Текстовая часть сообщения:\n"
                "TextPart(text='Привет, мир!')"
        ),
        GlobalVariable(
            name="FilePart",
            type="class",
            doc="Файловая часть сообщения:\n"
                "FilePart(file=FileWithBytes(name='doc.pdf', bytes=data))"
        ),
        GlobalVariable(
            name="DataPart",
            type="class",
            doc="Структурированные данные:\n"
                "DataPart(data={'result': 42, 'items': [1, 2, 3]})"
        ),
        GlobalVariable(
            name="Role",
            type="enum",
            doc="Роль в сообщении:\n"
                "• Role.user - сообщение пользователя\n"
                "• Role.agent - сообщение агента"
        ),
        GlobalVariable(
            name="Artifact",
            type="class",
            doc="Артефакт задачи:\n"
                "Artifact(artifactId='...', parts=[Part(...)])"
        ),
        GlobalVariable(
            name="httpx",
            type="module",
            doc="HTTP клиент для внешних API (точно как httpx):\n"
                "• response = await httpx.get(url, params={...})\n"
                "• response = await httpx.post(url, json={...})\n"
                "• response = await httpx.put(url, json={...})\n"
                "• response = await httpx.patch(url, json={...})\n"
                "• response = await httpx.delete(url)\n"
                "• response = await httpx.request(method, url, ...)\n"
                "• response.json() - получить JSON ответ\n"
                "• response.text - получить текст ответа\n"
                "• response.status_code - код статуса\n"
                "• response.headers - заголовки ответа"
        ),
    ]

    safe_builtins = [
        name for name in dir(builtins)
        if not name.startswith("_") and name not in BLOCKED_BUILTINS
    ]

    # Популярные модули для autocomplete (все разрешены кроме BLOCKED_MODULES)
    common_modules = [
        "json", "re", "datetime", "math", "typing", "collections",
        "itertools", "functools", "uuid", "hashlib", "base64",
        "urllib.parse", "random", "operator", "string", "decimal",
        "pydantic", "a2a", "a2a.types", "httpx", "copy", "time",
    ]

    state_fields = [
        StateField(
            name=f["name"],
            type=f["type"],
            description=f["description"],
            readonly=f["readonly"],
        )
        for f in STATE_FIELDS
    ]
    
    templates = [
        CodeTemplate(
            id=t["id"],
            name=t["name"],
            description=t["description"],
            code=t["code"],
            category=t["category"],
        )
        for t in CODE_TEMPLATES
    ]

    return CodeCompletionsResponse(
        modules=sorted(common_modules),
        globals=globals_list,
        builtins=sorted(safe_builtins),
        module_methods=MODULE_METHODS,
        state_fields=state_fields,
        templates=templates,
    )


class TemplatesResponse(BaseModel):
    """Список шаблонов кода"""
    templates: List[CodeTemplate]


@router.get("/templates", response_model=TemplatesResponse)
async def get_code_templates(
    category: Optional[str] = None,
    node_type: Optional[str] = None
) -> TemplatesResponse:
    """
    Возвращает список шаблонов кода.
    
    Args:
        category: Фильтр по категории (http, llm, interaction, data, files, state)
        node_type: Тип ноды (tool, function). По умолчанию tool.
    """
    source = FUNCTION_TEMPLATES if node_type == "function" else CODE_TEMPLATES
    
    templates = [
        CodeTemplate(
            id=t["id"],
            name=t["name"],
            description=t["description"],
            code=t["code"],
            category=t["category"],
        )
        for t in source
        if category is None or t["category"] == category
    ]
    
    return TemplatesResponse(templates=templates)


class SourceResponse(BaseModel):
    """Исходный код"""
    path: str
    source: Optional[str]
    error: Optional[str] = None


@router.get("/source")
async def get_function_source(function_path: str) -> SourceResponse:
    """
    Возвращает исходный код функции по её пути.
    
    Пример: agents.example_flow.functions.my_function
    """
    if not function_path:
        raise HTTPException(status_code=400, detail="function_path is required")

    return _get_source_by_path(function_path)


class AgentFunctionInfo(BaseModel):
    """Информация о функции из агента"""
    name: str
    path: str
    doc: Optional[str] = None


class AgentFunctionsResponse(BaseModel):
    """Список функций доступных в агенте"""
    agent_id: str
    functions: List[AgentFunctionInfo]
    error: Optional[str] = None


@router.get("/agent-functions")
async def get_agent_functions(agent_id: str) -> AgentFunctionsResponse:
    """
    Возвращает список функций из agents/<agent_id>/functions.py
    """
    if not agent_id:
        return AgentFunctionsResponse(
            agent_id=agent_id,
            functions=[],
            error="agent_id is required"
        )

    try:
        module_path = f"apps.agents.agents.{agent_id}.functions"
        module = importlib.import_module(module_path)

        functions = []
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if inspect.isfunction(obj):
                functions.append(AgentFunctionInfo(
                    name=name,
                    path=f"{module_path}.{name}",
                    doc=inspect.getdoc(obj)
                ))

        return AgentFunctionsResponse(
            agent_id=agent_id,
            functions=sorted(functions, key=lambda f: f.name)
        )
    except ModuleNotFoundError:
        return AgentFunctionsResponse(
            agent_id=agent_id,
            functions=[],
            error=f"Module agents.{agent_id}.functions not found"
        )
    except Exception as e:
        return AgentFunctionsResponse(
            agent_id=agent_id,
            functions=[],
            error=str(e)
        )


@router.get("/tool-source")
async def get_tool_source(tool_path: str) -> SourceResponse:
    """
    Возвращает исходный код tool класса по его пути.
    
    Пример: tools.calculator.Calculator
    """
    if not tool_path:
        raise HTTPException(status_code=400, detail="tool_path is required")

    return _get_source_by_path(tool_path)


def _get_source_by_path(path: str) -> SourceResponse:
    """
    Получает исходный код по пути к модулю/классу/функции/методу.
    
    Поддерживает:
    - module.function
    - module.ClassName
    - module.ClassName.method
    """
    try:
        parts = path.split(".")
        if len(parts) < 2:
            return SourceResponse(
                path=path,
                source=None,
                error="Invalid path format"
            )

        # Пробуем найти модуль, постепенно укорачивая путь
        obj = None
        for i in range(len(parts) - 1, 0, -1):
            module_path = ".".join(parts[:i])
            try:
                module = importlib.import_module(module_path)
                # Получаем оставшиеся части как атрибуты
                obj = module
                for attr_name in parts[i:]:
                    obj = getattr(obj, attr_name, None)
                    if obj is None:
                        break
                if obj is not None:
                    break
            except ModuleNotFoundError:
                continue

        if obj is None:
            return SourceResponse(
                path=path,
                source=None,
                error=f"Object not found: {path}"
            )

        source = inspect.getsource(obj)
        return SourceResponse(
            path=path,
            source=source
        )
    except ModuleNotFoundError:
        return SourceResponse(
            path=path,
            source=None,
            error="Module not found"
        )
    except OSError:
        return SourceResponse(
            path=path,
            source=None,
            error="Source code not available"
        )
    except TypeError:
        return SourceResponse(
            path=path,
            source=None,
            error="Cannot get source for built-in"
        )


# ============================================================================
# Валидация и выполнение кода
# ============================================================================

class ValidateRequest(BaseModel):
    """Запрос на валидацию кода"""
    code: str
    node_type: Optional[str] = "function"  # "function" или "tool"


class ValidateResponse(BaseModel):
    """Результат валидации"""
    valid: bool
    error: Optional[str] = None
    warnings: List[str] = []


class ParseSignatureRequest(BaseModel):
    """Запрос на парсинг сигнатуры функции"""
    code: str
    func_name: Optional[str] = None


class ParameterInfo(BaseModel):
    """Информация о параметре функции"""
    type: str
    description: str = ""
    default: Optional[Any] = None
    required: bool = True


class ParseSignatureResponse(BaseModel):
    """Результат парсинга сигнатуры"""
    success: bool
    func_name: Optional[str] = None
    parameters: Dict[str, ParameterInfo] = {}
    args_schema: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def _python_type_to_json_type(type_str: str) -> str:
    """Конвертирует Python тип в JSON Schema тип."""
    type_mapping = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "List": "array",
        "dict": "object",
        "Dict": "object",
        "Any": "string",
        "Optional": "string",
    }
    base_type = type_str.split("[")[0].strip()
    return type_mapping.get(base_type, "string")


def _parse_function_signature(code: str, func_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Парсит сигнатуру функции из Python кода.
    
    Args:
        code: Python код
        func_name: Имя функции (если None, ищет execute или run)
    
    Returns:
        Dict с информацией о функции
    """
    import ast
    
    tree = ast.parse(code)
    
    target_names = [func_name] if func_name else ["execute", "run"]
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in target_names or (func_name is None and not node.name.startswith("_")):
                params = {}
                args = node.args
                
                num_args = len(args.args)
                num_defaults = len(args.defaults)
                first_default_idx = num_args - num_defaults
                
                for i, arg in enumerate(args.args):
                    param_name = arg.arg
                    
                    if param_name in ("self", "cls", "state", "args"):
                        continue
                    
                    type_str = "string"
                    if arg.annotation:
                        type_str = ast.unparse(arg.annotation)
                    
                    has_default = i >= first_default_idx
                    default_value = None
                    if has_default:
                        default_idx = i - first_default_idx
                        default_node = args.defaults[default_idx]
                        try:
                            default_value = ast.literal_eval(default_node)
                        except (ValueError, TypeError):
                            default_value = ast.unparse(default_node)
                    
                    json_type = _python_type_to_json_type(type_str)
                    
                    params[param_name] = {
                        "type": json_type,
                        "python_type": type_str,
                        "required": not has_default,
                        "default": default_value,
                    }
                
                return {
                    "func_name": node.name,
                    "parameters": params,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                }
    
    raise ValueError(f"Функция не найдена: {target_names}")


@router.post("/parse-signature", response_model=ParseSignatureResponse)
async def parse_signature(request: ParseSignatureRequest) -> ParseSignatureResponse:
    """
    Парсит сигнатуру функции и генерирует args_schema.
    
    Извлекает параметры с type hints и default значениями,
    конвертирует в JSON Schema формат для LLM.
    """
    if not request.code or not request.code.strip():
        return ParseSignatureResponse(success=False, error="Код пустой")
    
    try:
        result = _parse_function_signature(request.code, request.func_name)
        
        args_schema = {}
        for param_name, param_info in result["parameters"].items():
            schema_item = {
                "type": param_info["type"],
                "description": f"Параметр {param_name}",
            }
            if param_info["default"] is not None:
                schema_item["default"] = param_info["default"]
            args_schema[param_name] = schema_item
        
        parameters = {
            name: ParameterInfo(
                type=info["type"],
                description=f"Параметр {name} ({info['python_type']})",
                default=info["default"],
                required=info["required"],
            )
            for name, info in result["parameters"].items()
        }
        
        return ParseSignatureResponse(
            success=True,
            func_name=result["func_name"],
            parameters=parameters,
            args_schema=args_schema,
        )
    
    except SyntaxError as e:
        return ParseSignatureResponse(success=False, error=f"Синтаксическая ошибка: {e}")
    except ValueError as e:
        return ParseSignatureResponse(success=False, error=str(e))
    except Exception as e:
        return ParseSignatureResponse(success=False, error=f"Ошибка парсинга: {e}")


class ExecuteRequest(BaseModel):
    """Запрос на выполнение кода или External API"""
    code: Optional[str] = None
    state: Dict[str, Any]
    func_name: Optional[str] = "run"
    # Для разных типов нод
    node_type: Optional[str] = "function"  # "function", "external_api", "remote_agent", "agent", "react_node", "tool"
    # external_api
    url: Optional[str] = None
    method: Optional[str] = "GET"
    auth_headers: Optional[Dict[str, str]] = None
    parameters: Optional[List[Dict[str, Any]]] = None
    state_mapping: Optional[Dict[str, str]] = None
    # remote_agent
    skill_id: Optional[str] = "default"
    input_mapping: Optional[Dict[str, Any]] = None
    # agent
    agent_id: Optional[str] = None
    # react_node / function / tool / external_api / agent / remote_agent config
    agent_config: Optional[Dict[str, Any]] = None
    node_config: Optional[Dict[str, Any]] = None  # альяс для agent_config
    # tool (ссылка на tool из библиотеки)
    tool_id: Optional[str] = None
    
    def model_post_init(self, __context):
        """Нормализуем node_config -> agent_config для унификации"""
        if self.node_config and not self.agent_config:
            self.agent_config = self.node_config


class DiffItem(BaseModel):
    """Элемент diff"""
    path: str
    old_value: Any
    new_value: Any
    change_type: str  # "added", "changed", "removed"


class ExecuteResponse(BaseModel):
    """Результат выполнения"""
    success: bool
    input_state: Optional[Dict[str, Any]] = None
    output_state: Optional[Dict[str, Any]] = None
    diff: List[DiffItem] = []
    error: Optional[str] = None
    duration_ms: int = 0


def _compute_diff(old: Dict[str, Any], new: Dict[str, Any], path: str = "") -> List[DiffItem]:
    """Вычисляет diff между двумя state."""
    diff_items = []

    # Для дебага показываем все изменения
    SKIP_KEYS = set()

    all_keys = set(old.keys()) | set(new.keys())

    for key in all_keys:
        current_path = f"{path}.{key}" if path else key

        if key in SKIP_KEYS:
            continue

        old_val = old.get(key)
        new_val = new.get(key)

        if key not in old:
            # Добавлено
            diff_items.append(DiffItem(
                path=current_path,
                old_value=None,
                new_value=new_val,
                change_type="added"
            ))
        elif key not in new:
            # Удалено
            diff_items.append(DiffItem(
                path=current_path,
                old_value=old_val,
                new_value=None,
                change_type="removed"
            ))
        elif isinstance(old_val, dict) and isinstance(new_val, dict):
            # Рекурсивно сравниваем вложенные dict
            diff_items.extend(_compute_diff(old_val, new_val, current_path))
        elif old_val != new_val:
            # Изменено
            diff_items.append(DiffItem(
                path=current_path,
                old_value=old_val,
                new_value=new_val,
                change_type="changed"
            ))

    return diff_items


@router.post("/validate", response_model=ValidateResponse)
async def validate_code(request: ValidateRequest) -> ValidateResponse:
    """
    Валидирует код без выполнения.
    
    Проверяет:
    - Синтаксис Python
    - Безопасность (запрещённые импорты, dunder атрибуты)
    - Наличие функции run() для function нод или execute() для tool нод
    """
    code = request.code
    node_type = request.node_type or "function"
    warnings = []

    if not code or not code.strip():
        return ValidateResponse(valid=False, error="Код пустой")

    try:
        # Проверка синтаксиса и безопасности
        _validate_code(code)

        # Для тулов проверяем функцию execute, для function нод - run
        if node_type == "tool":
            # Для тулов ищем execute (с автопоиском)
            try:
                compile_function(code, "execute", auto_find=True)
            except SafeEvalError as e:
                # Если execute не найден, проверяем есть ли вообще функции
                import re
                match = re.search(r"(?:async\s+)?def\s+(\w+)\s*\(", code)
                if not match:
                    return ValidateResponse(
                        valid=False, 
                        error="Function 'execute' not found in code. Tools must have 'execute' function."
                    )
                func_name = match.group(1)
                # Если найдена другая функция, это предупреждение, но не ошибка
                warnings.append(f"Найдена функция '{func_name}'. Для тулов рекомендуется использовать 'execute'")
            
            # Проверка async для execute
            if "async def execute" not in code and "def execute" in code:
                warnings.append("Рекомендуется использовать async def execute(args, state) для поддержки LLM вызовов")
        else:
            # Для function нод проверяем run
            compile_function(code, "run", auto_find=False)

            # Проверка async
            if "async def run" not in code and "def run" in code:
                warnings.append("Рекомендуется использовать async def run(state) для поддержки LLM вызовов")

        return ValidateResponse(valid=True, warnings=warnings)

    except SafeEvalError as e:
        return ValidateResponse(valid=False, error=str(e))
    except SyntaxError as e:
        return ValidateResponse(valid=False, error=f"Синтаксическая ошибка: {e}")
    except Exception as e:
        return ValidateResponse(valid=False, error=f"Ошибка: {e}")


@router.post("/execute", response_model=ExecuteResponse)
async def execute_code(request: ExecuteRequest) -> ExecuteResponse:
    """
    Выполняет ноду с переданным state.
    Использует унифицированную фабрику create_node() для всех типов нод.
    Возвращает diff между входным и выходным state.
    """
    input_state_raw = copy.deepcopy(request.state)
    start_time = time.time()

    try:
        # Нормализуем input_state один раз и используем те же значения в _execute_node
        input_state_normalized = copy.deepcopy(input_state_raw)
        task_id = input_state_normalized.setdefault("task_id", str(uuid.uuid4()))
        context_id = input_state_normalized.setdefault("context_id", str(uuid.uuid4()))
        input_state_normalized.setdefault("user_id", "test_user")
        agent_id = request.agent_id or "test-agent"
        if "session_id" not in input_state_normalized:
            input_state_normalized["session_id"] = f"{agent_id}:{context_id}"
        
        # Инициализируем поля по умолчанию ExecutionState для корректного diff
        input_state_normalized.setdefault("current_nodes", [])
        input_state_normalized.setdefault("skill_id", "default")
        input_state_normalized.setdefault("messages", [])
        input_state_normalized.setdefault("user_groups", [])
        input_state_normalized.setdefault("variables", {})
        input_state_normalized.setdefault("files", [])
        input_state_normalized.setdefault("interrupt_path", [])
        input_state_normalized.setdefault("node_history", {})
        input_state_normalized.setdefault("tool_results", {})
        input_state_normalized.setdefault("nested_states", {})
        input_state_normalized.setdefault("reasoning_history", [])
        input_state_normalized.setdefault("breakpoints", {})
        input_state_normalized.setdefault("scheduled_tasks", [])
        input_state_normalized.setdefault("prompt_history", [])
        # Опциональные поля которые ExecutionState.to_dict() включает
        input_state_normalized.setdefault("content", None)
        input_state_normalized.setdefault("response", None)
        input_state_normalized.setdefault("mock", None)
        input_state_normalized.setdefault("pending_reasoning", None)
        input_state_normalized.setdefault("breakpoint_hit", None)
        input_state_normalized.setdefault("breakpoint_state", None)
        input_state_normalized.setdefault("interrupt", None)
        
        node_config = await _build_node_config(request)
        output_state = await _execute_node(node_config, input_state_normalized, agent_id=agent_id)

        duration_ms = int((time.time() - start_time) * 1000)
        diff = _compute_diff(input_state_normalized, output_state)

        return ExecuteResponse(
            success=True,
            input_state=input_state_raw,
            output_state=output_state,
            diff=diff,
            duration_ms=duration_ms
        )

    except SafeEvalError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return ExecuteResponse(
            success=False,
            input_state=input_state_raw,
            error=str(e),
            duration_ms=duration_ms
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Ошибка выполнения: {e}", exc_info=True)
        return ExecuteResponse(
            success=False,
            input_state=input_state_raw,
            error=f"Ошибка выполнения: {e}",
            duration_ms=duration_ms
        )


async def _build_node_config(request: ExecuteRequest) -> Dict[str, Any]:
    """Конвертирует ExecuteRequest в node_config для create_node()."""
    node_type = request.node_type or "function"

    if node_type == "function":
        code = request.code
        if not code and request.agent_config:
            code = request.agent_config.get("code")
        if not code or not code.strip():
            raise SafeEvalError("Код пустой")
        return {
            "type": "function",
            "code": code,
        }

    elif node_type == "external_api":
        url = request.url
        method = request.method or "GET"
        auth_headers = request.auth_headers or {}
        parameters = request.parameters or []
        state_mapping = request.state_mapping or {}
        
        if not url and request.agent_config:
            url = request.agent_config.get("url")
            method = request.agent_config.get("method", "GET")
            auth_headers = request.agent_config.get("auth_headers", {})
            parameters = request.agent_config.get("parameters", [])
            state_mapping = request.agent_config.get("state_mapping", {})
        
        if not url:
            raise ValueError("URL обязателен для external_api")
        
        return {
            "type": "external_api",
            "url": url,
            "method": method,
            "auth_headers": auth_headers,
            "parameters": parameters,
            "state_mapping": state_mapping,
        }

    elif node_type == "remote_agent":
        url = request.url
        skill_id = request.skill_id or "default"
        auth_headers = request.auth_headers
        input_mapping = request.input_mapping
        
        if not url and request.agent_config:
            url = request.agent_config.get("url")
            skill_id = request.agent_config.get("skill_id", "default")
            auth_headers = request.agent_config.get("auth_headers")
            input_mapping = request.agent_config.get("input_mapping")
        
        if not url:
            raise ValueError("URL обязателен для remote_agent")
        
        return {
            "type": "remote_agent",
            "url": url,
            "skill_id": skill_id,
            "auth_headers": auth_headers,
            "input_mapping": input_mapping,
        }

    elif node_type == "agent":
        agent_id = request.agent_id
        skill_id = request.skill_id or "default"
        input_mapping = request.input_mapping
        
        if not agent_id and request.agent_config:
            agent_id = request.agent_config.get("agent_id")
            skill_id = request.agent_config.get("skill_id", "default")
            input_mapping = request.agent_config.get("input_mapping")
        
        if not agent_id:
            raise ValueError("agent_id обязателен для agent")
        
        return {
            "type": "agent",
            "agent_id": agent_id,
            "skill_id": skill_id,
            "input_mapping": input_mapping,
        }

    elif node_type == "react_node":
        agent_config = request.agent_config
        if not agent_config:
            raise ValueError("agent_config обязателен для react_node")
        prompt = agent_config.get("prompt")
        if not prompt:
            raise ValueError("Prompt обязателен для react_node")
        
        # Инлайним tools из БД
        container = get_container()
        tools = agent_config.get("tools", [])
        inlined_tools = await _inline_tools_list(tools, container)
        
        return {
            "type": "react_node",
            "prompt": prompt,
            "tools": inlined_tools,
            "llm": agent_config.get("llm", {}),
            "input_mapping": agent_config.get("input_mapping"),
        }

    elif node_type == "tool":
        tool_id = request.tool_id
        code = request.code
        input_mapping = request.input_mapping
        
        if not tool_id and not code and request.agent_config:
            tool_id = request.agent_config.get("tool_id")
            code = request.agent_config.get("code")
            input_mapping = request.agent_config.get("input_mapping")
        
        # Если есть код - это inline tool, не грузим из БД
        if code and code.strip():
            node_config = {
                "type": "tool",
                "code": code,
                "input_mapping": input_mapping,
            }
            
            # Добавляем дополнительные поля из agent_config если они есть
            if request.agent_config:
                for key in ["args_schema", "description", "tool_id", "name", "title", "tags", "tool_type", "permission"]:
                    if key in request.agent_config:
                        node_config[key] = request.agent_config[key]
            
            return node_config
        
        # Если нет кода, но есть tool_id - грузим из БД
        if tool_id:
            container = get_container()
            tool_ref = await container.tool_repository.get(tool_id)
            if not tool_ref:
                raise ValueError(f"Tool '{tool_id}' не найден в БД")
            if not tool_ref.code:
                raise ValueError(f"Tool '{tool_id}' не имеет inline code")
            
            args_schema = {}
            if tool_ref.args_schema:
                args_schema = {k: {"type": v.type, "description": v.description} for k, v in tool_ref.args_schema.items()}
            
            return {
                "type": "tool",
                "tool_id": tool_id,
                "code": tool_ref.code,
                "description": tool_ref.description,
                "args_schema": args_schema,
                "input_mapping": input_mapping,
            }
        
        raise SafeEvalError("Код пустой или tool_id не указан")

    raise ValueError(f"Неизвестный тип ноды: {node_type}")


async def _execute_node(node_config: Dict[str, Any], input_state: Dict[str, Any], agent_id: str = "test-agent") -> Dict[str, Any]:
    """Выполняет ноду используя унифицированную фабрику."""
    state_data = copy.deepcopy(input_state)
    # input_state уже должен быть нормализован с обязательными полями
    state_data.setdefault("task_id", str(uuid.uuid4()))
    state_data.setdefault("context_id", str(uuid.uuid4()))
    state_data.setdefault("user_id", "test_user")
    if "session_id" not in state_data:
        context_id = state_data.get("context_id", str(uuid.uuid4()))
        state_data["session_id"] = f"{agent_id}:{context_id}"
    
    node = await create_node("test_node", node_config)
    state = ExecutionState.model_validate(state_data)
    result_state = await node.run(state)
    return result_state.model_dump(exclude_none=False)

