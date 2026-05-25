"""
Модели для сервиса документации.
"""

from pydantic import BaseModel, Field

from core.types import JsonObject


class PlatformToolDoc(BaseModel):
    """Описание platform tool для документации редактора (LLM / inline)."""

    tool_id: str
    display_name: str
    source: str = Field(
        ...,
        description="database — запись в БД компании; registry_only — только процессный реестр",
    )
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    parameters_schema_json: str = "{}"
    code_mode: str | None = None
    mcp_server_id: str | None = None
    mcp_tool_name: str | None = None
    code_preview: str | None = None


class GlobalVariable(BaseModel):
    """Глобальная переменная доступная в inline коде."""

    name: str
    type: str
    doc: str
    perspective: list[str] | None = None  # в каких ракурсах доступна
    tags: list[str] | None = None


class DocumentationQuery(BaseModel):
    """Запрос документации с фильтрами и ракурсами."""

    # Язык программирования
    language: str = Field(default="python", description="python, javascript, typescript")

    # Ракурс (perspective) - для какого контекста нужна документация
    perspective: str = Field(default="editor", description="editor, flow, tool, node")

    # Фильтры
    categories: list[str] | None = Field(
        default=None,
        description="http, llm, data, files, interaction, state, logic, basic",
    )
    groups: list[str] | None = Field(default=None, description="Группы tools")
    tags: list[str] | None = Field(default=None, description="Произвольные теги")
    node_type: str | None = Field(
        default=None,
        description="function, tool, llm_node, external_api",
    )

    # Что включить в ответ
    include_modules: bool = True
    include_globals: bool = True
    include_templates: bool = True
    include_state_fields: bool = True
    include_builtins: bool = True

    # Сборка Markdown (to_markdown): полный перечень методов модулей и builtins
    markdown_expand_module_methods: bool = Field(
        default=True,
        description="False — в Markdown только список имён модулей, без методов.",
    )
    markdown_expand_builtins: bool = Field(
        default=True,
        description="False — в Markdown краткая отсылка к whitelist builtins, без списка имён.",
    )

    # Секция «Platform tools» в Markdown.
    include_platform_tools: bool = True

    # Заполняется вызывающим кодом (flows API): реестр + БД компании
    platform_tools: list[PlatformToolDoc] | None = None
    # Заполняется только из apps/flows (там же строится список без импорта core→apps)
    runtime_namespace_extras: list[GlobalVariable] | None = Field(
        default=None,
        description="Дополнительные runtime symbols для редактора, если вызывающий сервис их поддерживает.",
    )


class StateField(BaseModel):
    """Поле ExecutionState."""

    name: str
    type: str
    description: str
    readonly: bool = False


class ModuleMethod(BaseModel):
    """Метод модуля."""

    name: str
    type: str  # function, class, constant, decorator
    doc: str


class ModuleDoc(BaseModel):
    """Документация модуля."""

    name: str
    methods: list[ModuleMethod] = []
    description: str | None = None


class CodeTemplate(BaseModel):
    """Шаблон кода."""

    id: str
    name: str
    description: str
    code: str
    category: str
    node_type: str = "tool"  # tool или function
    tags: list[str] | None = None
    language: str = "python"
    parameters_schema: JsonObject | None = None


class DocumentationResponse(BaseModel):
    """Ответ с документацией."""

    language: str
    perspective: str

    modules: list[str] = []  # список доступных модулей
    module_methods: dict[str, list[ModuleMethod]] = {}  # методы модулей
    globals: list[GlobalVariable] = []
    builtins: list[str] = []
    state_fields: list[StateField] = []
    templates: list[CodeTemplate] = []
    platform_tools: list[PlatformToolDoc] = Field(default_factory=list)
    runtime_namespace_extras: list[GlobalVariable] | None = None
