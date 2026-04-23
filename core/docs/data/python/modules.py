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
    "urllib": [
        {
            "name": "parse",
            "type": "module",
            "doc": (
                "Разбор URL: `from urllib.parse import urlparse, urljoin, quote_plus, unquote, parse_qs`. "
                "Для HTTP к внешним URL в приоритете обёртка `httpx` из namespace."
            ),
        },
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
    "a2a": [
        {
            "name": "types",
            "type": "module",
            "doc": (
                "Типы протокола A2A: `from a2a.types import Message, Part, Role, TextPart, FilePart, DataPart, Artifact, ...`. "
                "Детали и примеры — блок `a2a.types` ниже; остальное — документация пакета a2a."
            ),
        },
    ],
    "asyncio": [
        {"name": "sleep", "type": "function", "doc": "Пауза: `await asyncio.sleep(seconds)`"},
        {"name": "gather", "type": "function", "doc": "Параллельно: `await asyncio.gather(c1, c2, return_exceptions=False)`"},
        {"name": "create_task", "type": "function", "doc": "Фон: `asyncio.create_task(coro())`"},
        {"name": "wait_for", "type": "function", "doc": "С таймаутом: `await asyncio.wait_for(aw, timeout=5.0)`"},
        {"name": "Semaphore", "type": "class", "doc": "`asyncio.Semaphore(n)` — ограничение параллелизма"},
        {"name": "Lock", "type": "class", "doc": "`asyncio.Lock()`"},
        {"name": "Event", "type": "class", "doc": "`asyncio.Event()`"},
    ],
    "ast": [
        {"name": "literal_eval", "type": "function", "doc": "Безопасный разбор литерала: `ast.literal_eval('{\"a\": 1}')`"},
        {"name": "parse", "type": "function", "doc": "Разбор исходника в AST: `ast.parse(code, mode='exec')`"},
        {"name": "dump", "type": "function", "doc": "Текстовое представление узла AST (отладка)"},
    ],
    "bisect": [
        {"name": "bisect_left", "type": "function", "doc": "Индекс вставки слева в отсортированной последовательности"},
        {"name": "bisect_right", "type": "function", "doc": "Индекс вставки справа"},
        {"name": "insort_left", "type": "function", "doc": "Вставить элемент, сохраняя порядок"},
        {"name": "insort_right", "type": "function", "doc": "Вставить справа от равных"},
    ],
    "calendar": [
        {"name": "monthcalendar", "type": "function", "doc": "Матрица дней месяца: `calendar.monthcalendar(year, month)`"},
        {"name": "month_name", "type": "constant", "doc": "Названия месяцев"},
        {"name": "day_name", "type": "constant", "doc": "Названия дней недели"},
        {"name": "isleap", "type": "function", "doc": "Високосный год: `calendar.isleap(year)`"},
    ],
    "copy": [
        {"name": "copy", "type": "function", "doc": "Неглубокая копия: `copy.copy(x)`"},
        {"name": "deepcopy", "type": "function", "doc": "Глубокая копия: `copy.deepcopy(x, memo=None)`"},
    ],
    "dataclasses": [
        {"name": "dataclass", "type": "decorator", "doc": "@dataclass — генерация __init__ и сравнения"},
        {"name": "field", "type": "function", "doc": "Поле с метаданными: `field(default=..., default_factory=...)`"},
        {"name": "asdict", "type": "function", "doc": "Экземпляр dataclass → dict"},
        {"name": "astuple", "type": "function", "doc": "Экземпляр dataclass → tuple"},
        {"name": "replace", "type": "function", "doc": "Копия с заменой полей: `replace(obj, **kwargs)`"},
    ],
    "decimal": [
        {"name": "Decimal", "type": "class", "doc": "Точные десятичные: `Decimal('0.1') + Decimal('0.2')`"},
        {"name": "getcontext", "type": "function", "doc": "Контекст округления"},
        {"name": "ROUND_HALF_UP", "type": "constant", "doc": "Режим округления"},
    ],
    "enum": [
        {"name": "Enum", "type": "class", "doc": "class Color(Enum): RED = 1"},
        {"name": "IntEnum", "type": "class", "doc": "Перечисление с int-значениями"},
        {"name": "auto", "type": "function", "doc": "Автозначение: `RED = auto()`"},
    ],
    "fractions": [
        {"name": "Fraction", "type": "class", "doc": "Дробь: `Fraction(3, 4)`"},
    ],
    "heapq": [
        {"name": "heappush", "type": "function", "doc": "Добавить в min-кучу"},
        {"name": "heappop", "type": "function", "doc": "Извлечь минимум"},
        {"name": "heapify", "type": "function", "doc": "Превратить список в кучу in-place"},
        {"name": "nlargest", "type": "function", "doc": "n наибольших: `heapq.nlargest(3, items, key=None)`"},
        {"name": "nsmallest", "type": "function", "doc": "n наименьших"},
    ],
    "html": [
        {"name": "escape", "type": "function", "doc": "Экранирование для HTML: `html.escape(s, quote=True)`"},
        {"name": "unescape", "type": "function", "doc": "Снять entity"},
    ],
    "ipaddress": [
        {"name": "ip_address", "type": "function", "doc": "IPv4/IPv6 объект: `ipaddress.ip_address('192.0.2.1')`"},
        {"name": "ip_network", "type": "function", "doc": "Сеть CIDR"},
        {"name": "IPv4Address", "type": "class", "doc": "IPv4 адрес"},
        {"name": "IPv6Address", "type": "class", "doc": "IPv6 адрес"},
    ],
    "logging": [
        {"name": "getLogger", "type": "function", "doc": "В sandbox предпочтительнее глобальный `logger`; для кастомного: `logging.getLogger('name')`"},
        {"name": "basicConfig", "type": "function", "doc": "Базовая настройка корневого логгера (осторожно в serverless)"},
        {"name": "INFO", "type": "constant", "doc": "Уровень INFO"},
        {"name": "WARNING", "type": "constant", "doc": "Уровень WARNING"},
        {"name": "ERROR", "type": "constant", "doc": "Уровень ERROR"},
    ],
    "markdown": [
        {"name": "markdown", "type": "function", "doc": "HTML из Markdown: `markdown.markdown(text, extensions=...)` — см. документацию библиотеки"},
    ],
    "mimetypes": [
        {"name": "guess_type", "type": "function", "doc": "MIME по пути: `mimetypes.guess_type('file.pdf')`"},
        {"name": "guess_extension", "type": "function", "doc": "Расширение по MIME"},
        {"name": "add_type", "type": "function", "doc": "Зарегистрировать тип"},
    ],
    "numbers": [
        {"name": "Integral", "type": "class", "doc": "ABC для целых"},
        {"name": "Real", "type": "class", "doc": "ABC для вещественных"},
        {"name": "Complex", "type": "class", "doc": "ABC для комплексных"},
    ],
    "operator": [
        {"name": "itemgetter", "type": "function", "doc": "Ключ сортировки: `sorted(rows, key=operator.itemgetter('id'))`"},
        {"name": "attrgetter", "type": "function", "doc": "Доступ к атрибуту"},
        {"name": "methodcaller", "type": "function", "doc": "Вызов метода по имени"},
        {"name": "eq", "type": "function", "doc": "operator.eq(a, b) и аналоги lt, le, gt, ge, ne"},
    ],
    "secrets": [
        {"name": "token_bytes", "type": "function", "doc": "Криптостойкие байты: `secrets.token_bytes(32)`"},
        {"name": "token_hex", "type": "function", "doc": "hex-строка"},
        {"name": "token_urlsafe", "type": "function", "doc": "urlsafe base64-подобная строка"},
        {"name": "choice", "type": "function", "doc": "Случайный элемент (криптостойко)"},
    ],
    "statistics": [
        {"name": "mean", "type": "function", "doc": "Среднее"},
        {"name": "median", "type": "function", "doc": "Медиана"},
        {"name": "stdev", "type": "function", "doc": "Выборочное стандартное отклонение"},
        {"name": "pstdev", "type": "function", "doc": "Статистическое отклонение популяции"},
        {"name": "quantiles", "type": "function", "doc": "Квантили"},
    ],
    "string": [
        {"name": "ascii_letters", "type": "constant", "doc": "a-zA-Z"},
        {"name": "digits", "type": "constant", "doc": "0-9"},
        {"name": "Template", "type": "class", "doc": "Шаблоны $placeholder: `Template('x=$y').substitute(y=1)`"},
        {"name": "Formatter", "type": "class", "doc": "Расширенное форматирование"},
    ],
    "time": [
        {"name": "time", "type": "function", "doc": "Unix timestamp: `time.time()`"},
        {"name": "sleep", "type": "function", "doc": "Синхронная пауза (сек); в async-коде предпочтительнее asyncio.sleep"},
        {"name": "strftime", "type": "function", "doc": "Форматирование локального времени"},
        {"name": "gmtime", "type": "function", "doc": "UTC struct_time"},
    ],
    "types": [
        {"name": "SimpleNamespace", "type": "class", "doc": "Объект с произвольными атрибутами: `types.SimpleNamespace(a=1)`"},
        {"name": "UnionType", "type": "class", "doc": "Отражение X | Y (Python 3.10+)"},
        {"name": "NoneType", "type": "class", "doc": "Тип None"},
    ],
    "typing": [
        {"name": "Optional", "type": "alias", "doc": "Optional[T] == Union[T, None]"},
        {"name": "Union", "type": "alias", "doc": "Union[A, B]"},
        {"name": "Literal", "type": "special", "doc": "Literal['a', 'b']"},
        {"name": "TypedDict", "type": "class", "doc": "class Row(TypedDict): id: str; name: str"},
        {"name": "Protocol", "type": "class", "doc": "Структурная типизация"},
        {"name": "Any", "type": "special", "doc": "Любой тип"},
        {"name": "Callable", "type": "special", "doc": "Callable[[int], str]"},
        {"name": "TypeVar", "type": "class", "doc": "T = TypeVar('T')"},
        {"name": "Generic", "type": "class", "doc": "Обобщённые классы"},
        {"name": "cast", "type": "function", "doc": "typing.cast(T, x) для type checkers"},
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
        {
            "name": "Message",
            "type": "class",
            "doc": (
                "Сообщение: `Message(messageId=str(uuid.uuid4()), role=Role.user, parts=[Part(root=TextPart(text='hi'))], "
                "metadata={})`. Роли: `Role.user`, `Role.agent`. Текст ответа LLM: "
                "`from a2a.utils.message import get_message_text` → `get_message_text(msg)`."
            ),
        },
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
        {
            "name": "AsyncClient",
            "type": "class",
            "doc": (
                "`async with httpx.AsyncClient(timeout=30.0) as client:` — в sandbox только "
                "`timeout=...` (без других аргументов конструктора); `client` поддерживает `get`, `post`, "
                "`put`, `patch`, `delete`, `request` с той же прокси-стратегией, что `httpx.get`. "
                "Вызовы к сервисам платформы — через `ServiceClient`, не через произвольный URL к внутренним API."
            ),
        },
        {
            "name": "RequestError",
            "type": "class",
            "doc": "Ошибка сетевого/транспортного уровня httpx: `except httpx.RequestError`.",
        },
        {
            "name": "get",
            "type": "function",
            "doc": (
                "`await httpx.get(url, *, params=None, headers=None, cookies=None, auth=None, "
                "follow_redirects=True, timeout=None, content=None)` — query-string через `params`, "
                "таймаут `timeout=10.0` или `httpx.Timeout(...)`. Ответ: `response.status_code`, "
                "`response.json()`, `response.text`, `response.headers`."
            ),
        },
        {
            "name": "post",
            "type": "function",
            "doc": (
                "`await httpx.post(url, *, json=None, data=None, content=None, files=None, "
                "params=None, headers=None, timeout=None)` — тело JSON через `json={...}`; "
                "сырой текст/bytes через `content=`; multipart — `files=`."
            ),
        },
        {
            "name": "put",
            "type": "function",
            "doc": "Как post: `json`, `content`, `headers`, `timeout`, `params`.",
        },
        {
            "name": "patch",
            "type": "function",
            "doc": "Как post: частичное обновление ресурса.",
        },
        {
            "name": "delete",
            "type": "function",
            "doc": "`await httpx.delete(url, *, params=None, headers=None, timeout=None)`.",
        },
        {
            "name": "request",
            "type": "function",
            "doc": (
                "`await httpx.request(method, url, *, json=None, content=None, params=None, headers=None, timeout=None)` — "
                "универсальный вызов."
            ),
        },
    ],
    "llm": [
        {
            "name": "chat",
            "type": "function",
            "doc": (
                "`await llm.chat(messages, *, response_model=None, tools=None, model=None, "
                "temperature=None, top_p=None, top_k=None, max_tokens=None, "
                "frequency_penalty=None, presence_penalty=None, seed=None, reasoning_effort=None, "
                "extra_body=None)` — `messages`: str | list | Message | dict; "
                "`tools`: OpenAI dict или `@tool` / BaseTool (`to_openai_schema`); "
                "`response_model`: Pydantic-модель для structured output; "
                "`extra_body`: dict полей тела запроса к провайдеру. Сырую `def` без `@tool` в tools нельзя."
            ),
        },
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
