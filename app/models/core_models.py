"""
Pydantic модели для конфигурации агентов и флоу.
Это источник правды для Storage, Migrator и FlowFactory.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any, Literal, TYPE_CHECKING
from enum import Enum
from datetime import datetime, timezone, timedelta
import json
from ..core.config import settings
from ..fields import Field

from .rag_models import AgentRAGConfig

if TYPE_CHECKING:
    from .context_models import Context


class HistorySource(str):
    """Специальный тип для источника истории диалогов"""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, list) and all(isinstance(item, str) for item in v):
            return v
        raise ValueError("history_from должен быть строкой, списком строк или None")

    def __repr__(self):
        return f"HistorySource({super().__repr__()})"


class NodeType(str, Enum):
    """Типы нод в графе"""

    AGENT_NODE = "agent_node"
    TOOL_NODE = "tool_node"
    FUNCTION_NODE = "function_node"
    FLOW_NODE = "flow_node"
    CONDITIONAL_EDGE = "conditional_edge"
    MESSAGE_NODE = "message_node"


class AgentType(str, Enum):
    """Типы агентов"""

    REACT = "react"
    STATEGRAPH = "stategraph"


class CodeMode(str, Enum):
    """Режим хранения кода"""

    CODE_REFERENCE = "code_reference"  # Ссылка на код в файлах
    INLINE_CODE = "inline_code"  # Код хранится в БД


class ConditionType(str, Enum):
    """Типы условий в графе"""

    ROUTER = "router"  # Функция возвращает ID следующей ноды
    EXPRESSION = "expression"  # Простое условное выражение (true/false)


class GraphNode(BaseModel):
    """Нода в графе"""

    id: str = Field(
        title="ID ноды",
        description="Уникальный идентификатор ноды в графе",
        readonly=True,
    )
    type: NodeType = Field(title="Тип ноды", description="Тип ноды в графе")
    params: Dict[str, Any] = Field(
        default_factory=dict,
        title="Параметры",
        description="Параметры ноды",
    )

    # Режим хранения кода ноды
    code_mode: CodeMode = Field(
        default=CodeMode.CODE_REFERENCE,
        title="Режим кода",
        description="Режим хранения кода ноды",
    )

    # Для CODE_REFERENCE режима
    function_class: Optional[str] = Field(
        default=None,
        title="Класс функции",
        description="Путь к классу агента",
        placeholder="app.agents.calculator.CalculatorAgent",
    )
    function_path: Optional[str] = Field(
        default=None,
        title="Путь к функции",
        description="Путь к функции",
        placeholder="app.tools.calc_tools.add_numbers",
    )

    # Для INLINE_CODE режима
    inline_code: Optional[str] = Field(
        default=None,
        title="Инлайн код",
        description="Python код ноды",
        widget_attrs={"rows": 10, "class": "code-editor"},
    )
    prompt: Optional[str] = Field(
        default='.',
        title="Промпт",
        description="Промпт для ReAct нод",
        widget_attrs={"rows": 5},
    )

    # Маппинг данных
    input_mapping: Optional[Dict[str, str]] = Field(
        default=None,
        title="Маппинг входных данных",
        description="Как брать данные из state",
    )
    output_mapping: Optional[Dict[str, str]] = Field(
        default=None,
        title="Маппинг выходных данных",
        description="Как сохранять результат в state",
    )


class GraphEdge(BaseModel):
    """Ребро в графе"""

    source: str = Field(title="Источник", description="ID исходной ноды")
    target: str = Field(title="Цель", description="ID целевой ноды")
    condition: Optional[str] = Field(
        default=None,
        title="Условие",
        description="Условие или выражение для перехода",
        widget_attrs={"rows": 3},
    )
    condition_type: ConditionType = Field(
        default=ConditionType.EXPRESSION,
        title="Тип условия",
        description="Тип условия для перехода",
    )


class BuilderEntity(BaseModel):
    """Базовая модель для всех сущностей Builder с автоматическим преобразованием типов"""
    
    model_config = {"str_strip_whitespace": True}
    
    # Метаданные - общие для всех сущностей
    source: str = Field(
        default="manual",
        title="Источник",
        description="Источник создания (manual, migration, canvas_created)",
        readonly=True,
    )
    created_at: Optional[datetime] = Field(
        default=None, title="Создан", description="Дата создания", readonly=True
    )
    updated_at: Optional[datetime] = Field(
        default=None, title="Обновлен", description="Дата обновления", readonly=True
    )
    
    @staticmethod
    def parse_json_string(v: Any) -> Any:
        """Преобразует JSON строку в dict/list"""
        if isinstance(v, str) and v.strip():
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v if v else None


class GraphDefinition(BaseModel):
    """Определение графа"""

    nodes: List[GraphNode] = Field(
        title="Ноды",
        description="Список нод в графе",
    )
    edges: List[GraphEdge] = Field(
        title="Ребра",
        description="Список ребер в графе",
    )
    entry_point: str = Field(
        title="Точка входа",
        description="ID ноды, с которой начинается выполнение графа",
    )


class ToolReference(BuilderEntity):
    """Ссылка на инструмент"""

    class Config:
        storage_prefix = "tool"

    tool_id: str = Field(
        frozen=True,
        title="ID инструмента",
        description="ID инструмента (путь к функции, ID агента, MCP tool)",
        pattern=r"^[a-zA-Z0-9_.:/-]+$",
    )
    title: Optional[str] = Field(
        default=None,
        title="Название",
        description="Название для отображения в UI",
        placeholder="Красивое название функции"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        title="Параметры",
        description="Параметры инструмента",
    )

    # Новые поля для поддержки inline кода
    code_mode: CodeMode = Field(
        default=CodeMode.CODE_REFERENCE,
        title="Режим кода",
        description="Режим хранения кода инструмента",
    )
    function_path: Optional[str] = Field(
        default=None,
        title="Путь к функции",
        description="Путь к функции для CODE_REFERENCE",
        placeholder="app.tools.calc_tools.add_numbers",
    )
    inline_code: Optional[str] = Field(
        default=None,
        title="Инлайн код",
        description="Python код для INLINE_CODE",
        widget_attrs={"rows": 8, "class": "code-editor"},
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание",
        description="Описание инструмента",
        widget_attrs={"rows": 3},
    )
    
    # Поля для биллинга и доступа
    cost: float = Field(
        default=0.0,
        title="Стоимость",
        description="Стоимость вызова инструмента в RUB",
        ge=0.0,
        widget_attrs={"step": "0.001", "placeholder": "0.001"}
    )
    billing_name: Optional[str] = Field(
        default=None,
        title="Название для биллинга",
        description="Название для учета использования (по умолчанию tool_id)",
        placeholder="weather_api"
    )
    free_for_plans: List[str] = Field(
        default_factory=list,
        title="Бесплатно для планов",
        description="Тарифные планы для которых инструмент бесплатен",
        widget_attrs={"multiple": True}
    )
    tariff_limits: Dict[str, int] = Field(
        default_factory=dict,
        title="Лимиты по тарифам",
        description="Лимиты использования по тарифным планам (-1 = без лимитов, 0 = запрещено)",
        widget_attrs={"rows": 4, "placeholder": '{"free": 10, "basic": 100, "premium": -1}'}
    )
    is_public: bool = Field(
        default=False,
        title="Публичный",
        description="Доступен ли инструмент в публичном редакторе ботов"
    )


class LLMConfig(BaseModel):
    """Конфигурация LLM"""

    provider: str = Field(
        default="openai",
        title="Провайдер",
        description="Провайдер LLM (openai, anthropic, yandex, etc.)",
    )
    model: str = Field(
        default="gpt-4",
        title="Модель",
        description="Название модели",
        placeholder="gpt-4, claude-3-sonnet, yandexgpt",
    )
    temperature: float = Field(
        default=0.2,
        title="Температура",
        description="Температура для генерации (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )
    max_tokens: Optional[int] = Field(
        default=None,
        title="Максимум токенов",
        description="Максимальное количество токенов в ответе",
        ge=1,
    )
    api_key: Optional[str] = Field(
        default=None,
        title="API ключ",
        description="API ключ для провайдера",
    )
    base_url: Optional[str] = Field(
        default=None,
        title="Базовый URL",
        description="Базовый URL для API",
        placeholder="https://api.openai.com/v1",
    )
    additional_params: Dict[str, Any] = Field(
        default_factory=dict,
        title="Дополнительные параметры",
        description="Дополнительные параметры для LLM",
    )


class AgentConfig(BuilderEntity):
    """Конфигурация агента"""

    class Config:
        storage_prefix = "agent"

    agent_id: str = Field(
        ...,
        frozen=True,
        title="ID агента",
        description="Уникальный идентификатор агента",
        readonly=True,
    )
    name: str = Field(
        title="Название", description="Название агента", placeholder="Мой агент"
    )
    title: Optional[str] = Field(
        default=None,
        title="Название для UI",
        description="Название для отображения в списке способностей (по умолчанию name)",
        placeholder="Красивое название агента"
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание",
        description="Описание агента",
        widget_attrs={"rows": 4},
    )
    type: AgentType = Field(
        default=AgentType.REACT,
        title="Тип агента",
        description="Тип агента (ReAct или StateGraph)",
    )

    # Режим хранения кода
    code_mode: CodeMode = Field(
        default=CodeMode.CODE_REFERENCE,
        title="Режим кода",
        description="Режим хранения кода агента",
    )

    # Для CODE_REFERENCE режима
    function_class: Optional[str] = Field(
        default=None,
        title="Класс агента",
        description="Путь к классу-наследнику BaseAgent",
        placeholder="app.agents.calculator.CalculatorAgent",
    )

    # Для INLINE_CODE режима
    inline_code: Optional[str] = Field(
        default=None,
        title="Инлайн код",
        description="Python код агента",
        widget_attrs={"rows": 15, "class": "code-editor"},
    )

    # Поля для ReAct агентов
    prompt: Optional[str] = Field(
        default=None,
        title="Промпт",
        description="Системный промпт для ReAct агента (используйте {variable} для подстановки)",
        widget_attrs={"rows": 8},
    )

    # Поля для StateGraph агентов
    graph_definition: Optional[GraphDefinition] = Field(
        default=None,
        title="Определение графа",
        description="Определение графа для StateGraph агента",
    )

    # Общие поля
    tools: List[ToolReference] = Field(
        default_factory=list,
        title="Инструменты",
        description="Список инструментов агента",
    )
    llm_config: Optional[LLMConfig] = Field(
        default=None,
        title="Конфигурация LLM",
        description="Конфигурация языковой модели",
    )

    # История диалогов
    history_from: Optional[HistorySource] = Field(
        default=None,
        title="История от",
        description="Источник истории диалогов (global, список агентов или None)",
        placeholder="global или agent1,agent2",
    )
    
    # Локальные переменные агента
    local_variables: Dict[str, Any] = Field(
        default_factory=dict,
        title="Локальные переменные",
        description="Переменные доступные только в этом агенте (перекрывают переменные flow)",
        widget_attrs={"rows": 4, "placeholder": '{"max_attempts": 3, "greeting": "Привет!"}'}
    )
    
    # Публичность агента
    is_public: bool = Field(
        default=False,
        title="Публичный",
        description="Доступен ли агент как инструмент в публичном редакторе ботов"
    )


class FlowConfig(BuilderEntity):
    """Конфигурация флоу - простая административная сущность"""

    class Config:
        storage_prefix = "flow"

    flow_id: Optional[str] = Field(
        default=None,
        frozen=True,
        title="ID флоу",
        description="Уникальный идентификатор флоу",
        readonly=True,
    )
    name: str = Field(
        title="Название", description="Название флоу", placeholder="Мой флоу"
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание",
        description="Описание флоу",
        widget_attrs={"rows": 4},
    )

    # Точка входа - агент который обрабатывает запросы
    entry_point_agent: str = Field(
        title="Агент точки входа",
        description="ID агента который обрабатывает запросы",
        placeholder="app.agents.calculator.agent.CalculatorAgent",
    )

    # Платформы на которых работает flow с настройками
    platforms: Dict[str, Dict[str, Any]] = Field(
        default_factory=lambda: {"api": {}},
        title="Платформы",
        description="Платформы на которых работает флоу с настройками",
    )

    # Настройки выполнения
    timeout: Optional[int] = Field(
        default=None, title="Таймаут", description="Таймаут выполнения в секундах", ge=1
    )
    max_retries: int = Field(
        default=0,
        title="Максимум повторов",
        description="Максимальное количество повторов при ошибке",
        ge=0,
    )
    
    # Переменные флоу
    variables: Dict[str, Any] = Field(
        default_factory=dict,
        title="Переменные",
        description="Переменные доступные во всех агентах флоу (используйте {variable} в промптах)",
        widget_attrs={"rows": 6, "placeholder": '{"bot_name": "Помощник", "timeout_minutes": 30}'}
    )
    
    # RAG конфигурация для flow
    rag_config: Optional[AgentRAGConfig] = Field(
        default_factory=lambda: AgentRAGConfig(
            enabled=True,
            namespace_scope="flow",
            search_scopes=["flow", "company"],
            auto_index_messages=False
        ),
        title="RAG конфигурация",
        description="Настройки базы знаний для агентов в этом flow"
    )
    
    # Публичность
    is_public: bool = Field(
        default=False,
        title="Публичный",
        description="Доступен ли flow для копирования в новые компании"
    )

    # Данные канваса Builder
    canvas_data: Optional[Dict[str, Any]] = Field(
        default=None,
        title="Данные канваса",
        description="Позиции элементов и связи на канвасе Builder",
        exclude_from_form=True,
    )
    
    @field_validator('platforms', 'canvas_data', 'variables', mode='before')
    @classmethod
    def parse_json_fields(cls, v):
        """Автоматически парсит JSON строки в dict"""
        if isinstance(v, str) and v.strip():
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v if v else ({"api": {}} if v is None else v)
    
    @field_validator('timeout', mode='before')
    @classmethod
    def parse_timeout(cls, v):
        """Преобразует пустую строку в None для timeout"""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v
    
    @field_validator('max_retries', mode='before')
    @classmethod
    def parse_max_retries(cls, v):
        """Преобразует пустую строку в 0 для max_retries"""
        if isinstance(v, str) and v.strip() == "":
            return 0
        return v
    
    @field_validator('rag_config', mode='before')
    @classmethod
    def ensure_rag_config(cls, v):
        """Создаёт дефолтный RAG конфиг если он None (для старых flow)"""
        if v is None:
            return AgentRAGConfig(
                enabled=True,
                namespace_scope="flow",
                search_scopes=["flow", "company"],
                auto_index_messages=False
            )
        return v


class TaskStatus(str, Enum):
    """Статусы задач"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_FOR_INPUT = "waiting_for_input"


class TaskConfig(BaseModel):
    """Конфигурация задачи"""

    class Config:
        storage_prefix = "task"

    task_id: str = Field(
        title="ID задачи", description="Уникальный идентификатор задачи", readonly=True
    )
    flow_id: str = Field(title="ID флоу", description="Идентификатор флоу для задачи")
    context: Any = Field(
        title="Контекст",
        description="Контекст выполнения задачи",
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        title="Статус",
        description="Статус выполнения задачи",
    )
    input_data: Dict[str, Any] = Field(
        default_factory=dict,
        title="Входные данные",
        description="Входные данные для задачи",
    )
    output_data: Optional[Dict[str, Any]] = Field(
        default=None,
        title="Выходные данные",
        description="Результат выполнения задачи",
        readonly=True,
    )
    error_message: Optional[str] = Field(
        default=None,
        title="Сообщение об ошибке",
        description="Сообщение об ошибке при выполнении",
        readonly=True,
    )
    created_at: Optional[datetime] = Field(
        default=None,
        title="Создано",
        description="Время создания задачи",
        readonly=True,
    )
    started_at: Optional[datetime] = Field(
        default=None,
        title="Запущено",
        description="Время начала выполнения",
        readonly=True,
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        title="Завершено",
        description="Время завершения выполнения",
        readonly=True,
    )
    
    @field_validator('context', mode='before')
    @classmethod
    def validate_context(cls, v):
        """Преобразует dict в Context если нужно"""
        if v is None or not isinstance(v, dict):
            return v
        from .context_models import Context
        return Context(**v)

    # Свойства для обратной совместимости
    @property
    def user_id(self) -> str:
        return self.context.user.user_id

    @property
    def session_id(self) -> str:
        return self.context.session_id or ""

    @property
    def platform(self) -> str:
        return self.context.platform


class SessionStatus(str, Enum):
    """Статусы сессии"""

    ACTIVE = "active"
    PROCESSING = "processing"  # Агент обрабатывает запрос
    WAITING_INPUT = "waiting_input"  # Ждет ответа на interrupt
    INACTIVE = "inactive"
    EXPIRED = "expired"


class SessionConfig(BaseModel):
    """Конфигурация сессии"""

    session_id: str = Field(
        title="ID сессии", description="Уникальный идентификатор сессии", readonly=True
    )
    platform: str = Field(
        title="Платформа",
        description="Платформа (telegram, api, web)",
    )
    user_id: str = Field(
        title="ID пользователя", description="Идентификатор пользователя"
    )
    flow_id: str = Field(title="ID флоу", description="Идентификатор флоу")
    status: SessionStatus = Field(
        default=SessionStatus.ACTIVE,
        title="Статус",
        description="Статус сессии",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные метаданные сессии",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        title="Создано",
        description="Время создания сессии",
        readonly=True,
    )
    last_activity: Optional[datetime] = Field(
        default=None,
        title="Последняя активность",
        description="Время последней активности",
        readonly=True,
    )
    message_count: int = Field(
        default=0,
        title="Количество сообщений",
        description="Общее количество сообщений в сессии",
    )
    first_message: Optional[str] = Field(
        default=None,
        title="Первое сообщение",
        description="Первое сообщение пользователя (превью)",
    )

    @property
    def session_key(self) -> str:
        key = self.session_id.split("_")[-1]
        return f"session:{self.platform}:{self.user_id}:{self.flow_id}:{key}"


class CloudVoiceTokenConfig(BaseModel):
    """Конфигурация токенов Cloud Voice API"""
    
    client_id: str = Field(
        title="Client ID",
        description="Идентификатор клиента Cloud Voice API"
    )
    access_token: str = Field(
        title="Access Token",
        description="Токен доступа к API"
    )
    refresh_token: str = Field(
        title="Refresh Token", 
        description="Токен для обновления access_token"
    )
    expires_at: datetime = Field(
        title="Время истечения",
        description="Время когда истекает access_token"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Время создания",
        description="Время создания токена"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Время обновления",
        description="Время последнего обновления токена"
    )
    
    def is_expired(self) -> bool:
        """Проверяет истек ли access_token"""
        return datetime.now(timezone.utc) >= self.expires_at
    
    def is_refresh_expired(self, refresh_ttl_days: int = 30) -> bool:
        """Проверяет истек ли refresh_token (по умолчанию 30 дней)"""
        refresh_expires_at = self.created_at + timedelta(days=refresh_ttl_days)
        return datetime.now(timezone.utc) >= refresh_expires_at


class FileStatus(str, Enum):
    """Статус файла"""

    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    FAILED = "failed"
    DELETED = "deleted"


class FileRecord(BaseModel):
    """Запись о файле в системе"""

    file_id: str = Field(
        title="ID файла", description="Уникальный ID файла в системе", readonly=True
    )
    provider: str = Field(
        title="Провайдер",
        description="Провайдер S3 (aws, yandex, minio, etc.)",
    )
    original_name: str = Field(
        title="Оригинальное имя", description="Оригинальное имя файла"
    )
    s3_key: str = Field(title="Ключ S3", description="Ключ файла в S3", readonly=True)
    s3_bucket: str = Field(title="Bucket S3", description="Bucket в S3", readonly=True)
    s3_endpoint: Optional[str] = Field(
        default=None,
        title="Endpoint S3",
        description="Endpoint URL провайдера",
        readonly=True,
    )
    content_type: str = Field(
        title="Тип содержимого", description="MIME тип файла", readonly=True
    )
    file_size: int = Field(
        title="Размер файла", description="Размер файла в байтах", readonly=True
    )
    checksum: Optional[str] = Field(
        default=None,
        title="Контрольная сумма",
        description="MD5 или другая контрольная сумма",
        readonly=True,
    )
    status: FileStatus = Field(
        default=FileStatus.UPLOADING,
        title="Статус",
        description="Статус файла",
        readonly=True,
    )
    uploaded_by: Optional[str] = Field(
        default=None,
        title="Загрузил",
        description="ID пользователя который загрузил",
        readonly=True,
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные метаданные файла",
    )
    tags: List[str] = Field(
        default_factory=list,
        title="Теги",
        description="Теги для категоризации",
    )
    is_public: bool = Field(
        default=False,
        title="Публичный",
        description="Доступен ли файл без авторизации",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создан",
        description="Время создания файла",
        readonly=True,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Обновлен",
        description="Время обновления файла",
        readonly=True,
    )

    @property
    def key(self) -> str:
        """Ключ для хранения в БД"""
        return f"s3:{self.provider}:{self.file_id}"

    @property
    def url(self) -> Optional[str]:
        """URL для скачивания файла через нашу платформу"""
        if not self.file_id:
            return None

        from ..core.context import get_context
        context = get_context()
        subdomain = context.active_company.subdomain
        
        # На проде используется nginx/reverse proxy на стандартных портах
        if settings.server.env == "local":
            # Локально добавляем порт
            base_url = f"http://{subdomain}.{settings.server.domain}:{settings.server.port}"
        else:
            # На проде порт не нужен (nginx на 80/443)
            protocol = "https" if settings.server.env in ["production", "testing"] else "http"
            base_url = f"{protocol}://{subdomain}.{settings.server.domain}"
        
        return f"{base_url}/api/v1/files/download/{self.file_id}"

    @property
    def direct_s3_url(self) -> Optional[str]:
        """Прямая ссылка на S3 (для внутреннего использования)"""
        if not self.s3_bucket or not self.s3_key or not self.s3_endpoint:
            return None

        base_url = self.s3_endpoint.rstrip("/")
        return f"{base_url}/{self.s3_bucket}/{self.s3_key}"


class AudioRecord(FileRecord):
    """Запись об аудиофайле в системе - наследуется от FileRecord"""
    
    duration: Optional[float] = Field(
        default=None,
        title="Длительность", 
        description="Длительность аудио в секундах",
        readonly=True
    )
    
    # Результаты распознавания речи
    recognition_text: Optional[str] = Field(
        default=None,
        title="Распознанный текст",
        description="Результат распознавания речи",
        readonly=True
    )
    recognition_confidence: Optional[float] = Field(
        default=None,
        title="Уверенность распознавания",
        description="Уверенность распознавания от 0.0 до 1.0",
        readonly=True
    )
    recognition_qid: Optional[str] = Field(
        default=None,
        title="QID Cloud Voice",
        description="ID запроса к Cloud Voice API",
        readonly=True
    )

    @property
    def audio_id(self) -> str:
        """Алиас для file_id для обратной совместимости"""
        return self.file_id
    
    @property
    def key(self) -> str:
        """Ключ для хранения в БД"""
        return f"audio:{self.provider}:{self.file_id}"


