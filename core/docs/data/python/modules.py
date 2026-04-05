"""
Документация модулей Python.
"""

from typing import Any, Dict, List

from core.inline_python_eval_policy import ALLOWED_IMPORT_ROOTS

# Импорты в inline-коде flows: whitelist (см. core.inline_python_eval_policy).
COMMON_MODULES: List[str] = sorted(
    m for m in ALLOWED_IMPORT_ROOTS if m != "__future__"
)

# Методы модулей для autocomplete
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
        {"name": "BaseModel", "type": "class", "doc": "Базовый класс модели: class User(BaseModel): name: str"},
        {"name": "Field", "type": "function", "doc": "Поле: name: str = Field(..., min_length=1)"},
        {"name": "field_validator", "type": "decorator", "doc": "Валидатор поля (v2): @field_validator('email')"},
        {"name": "model_validator", "type": "decorator", "doc": "Валидатор модели (v2): @model_validator(mode='after')"},
    ],
    "a2a.types": [
        {"name": "Message", "type": "class", "doc": "A2A сообщение: Message(messageId, role, parts, metadata)"},
        {"name": "Part", "type": "class", "doc": "Часть сообщения: Part(root=TextPart(text='...'))"},
        {"name": "TextPart", "type": "class", "doc": "Текстовая часть: TextPart(text='Привет')"},
        {"name": "FilePart", "type": "class", "doc": "Файл: FilePart(file=FileWithBytes(name, bytes=base64_str, mime_type))"},
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
        {"name": "chat", "type": "function", "doc": """await llm.chat(..., tools=[...]). tools: OpenAI dict или объекты @tool / BaseTool (to_openai_schema). Сырую def без @tool не передавать."""},
    ],
    "context": [
        {"name": "channel", "type": "property", "doc": "Канал: 'a2a', 'api', 'telegram', 'max', 'voip'"},
        {"name": "user_id", "type": "property", "doc": "ID пользователя"},
        {"name": "session_id", "type": "property", "doc": "ID сессии"},
        {"name": "flow_id", "type": "property", "doc": "ID агента"},
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
        {"name": "get", "type": "method", "doc": "state.get('key', default) — как у dict"},
        {"name": "model_dump", "type": "method", "doc": "Сериализация в dict: state.model_dump()"},
    ],
}
