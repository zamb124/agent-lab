"""
Модели для сервиса документации.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PlatformToolDoc(BaseModel):
    """Описание platform tool для документации редактора (LLM / inline)."""

    tool_id: str
    display_name: str
    source: str = Field(
        ...,
        description="database — запись в БД компании; registry_only — только процессный реестр",
    )
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    args_schema_json: str = "{}"
    code_mode: Optional[str] = None
    mcp_server_id: Optional[str] = None
    mcp_tool_name: Optional[str] = None
    code_preview: Optional[str] = None


class DocumentationQuery(BaseModel):
    """Запрос документации с фильтрами и ракурсами."""

    # Язык программирования
    language: str = Field(default="python", description="python, javascript, typescript")

    # Ракурс (perspective) - для какого контекста нужна документация
    perspective: str = Field(default="editor", description="editor, flow, tool, node")

    # Фильтры
    categories: Optional[List[str]] = Field(
        default=None,
        description="http, llm, data, files, interaction, state, logic, basic",
    )
    groups: Optional[List[str]] = Field(default=None, description="Группы tools")
    tags: Optional[List[str]] = Field(default=None, description="Произвольные теги")
    node_type: Optional[str] = Field(
        default=None,
        description="function, tool, llm_node, external_api",
    )

    # Что включить в ответ
    include_modules: bool = True
    include_globals: bool = True
    include_templates: bool = True
    include_state_fields: bool = True
    include_builtins: bool = True

    # Заполняется вызывающим кодом (flows API): реестр + БД компании
    platform_tools: Optional[List[PlatformToolDoc]] = None


class GlobalVariable(BaseModel):
    """Глобальная переменная доступная в inline коде."""
    name: str
    type: str
    doc: str
    perspective: Optional[List[str]] = None  # в каких ракурсах доступна
    tags: Optional[List[str]] = None


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
    methods: List[ModuleMethod] = []
    description: Optional[str] = None


class CodeTemplate(BaseModel):
    """Шаблон кода."""
    id: str
    name: str
    description: str
    code: str
    category: str
    node_type: str = "tool"  # tool или function
    tags: Optional[List[str]] = None
    language: str = "python"


class DocumentationResponse(BaseModel):
    """Ответ с документацией."""
    language: str
    perspective: str
    
    modules: List[str] = []  # список доступных модулей
    module_methods: Dict[str, List[ModuleMethod]] = {}  # методы модулей
    globals: List[GlobalVariable] = []
    builtins: List[str] = []
    state_fields: List[StateField] = []
    templates: List[CodeTemplate] = []
    platform_tools: List[PlatformToolDoc] = Field(default_factory=list)
