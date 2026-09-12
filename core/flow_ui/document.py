"""Flow UI: грамматика блоков и документа интерфейса flow.

Pydantic-модели этого модуля — единственная спецификация интерфейса: из них
строится JSON Schema для редактора (палитра, свойства, валидация), для
structured output тулов ``llm_node`` и для code-node SDK.

Строковые свойства, помеченные :class:`FlowUIText`, — текстовые шаблоны
платформенной грамматики (``{email}``, ``{customer.name}``, ``{?path}``), той же,
что и в промптах ``llm_node``. Свойства :class:`FlowUIStatePath` — путь к полю
``ExecutionState``. Адресное пространство одно на всю платформу.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import ConfigDict, Field, GetJsonSchemaHandler, StringConstraints, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

from core.models.base import StrictBaseModel
from core.types import JsonObject, JsonValue

STATE_PATH_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$"
BLOCK_ID_PATTERN = r"^[a-z][a-z0-9_-]*$"
PAGE_ID_PATTERN = r"^[a-z][a-z0-9_-]*$"
ACTION_NAME_PATTERN = r"^[a-z][a-z0-9_]*$"

FlowUIBlockGroup = Literal["layout", "content", "input", "action", "data", "platform", "custom"]


class FlowUITemplateText:
    """Маркер Annotated: строка является текстовым шаблоном ``{path}``."""

    def __get_pydantic_json_schema__(
        self, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(schema)
        json_schema["x-flow-ui"] = "template"
        return json_schema


class FlowUIStatePathMarker:
    """Маркер Annotated: строка — путь к полю ExecutionState."""

    def __get_pydantic_json_schema__(
        self, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(schema)
        json_schema["x-flow-ui"] = "state_path"
        return json_schema


FlowUIText = Annotated[str, FlowUITemplateText()]
FlowUIStatePath = Annotated[
    str, StringConstraints(pattern=STATE_PATH_PATTERN), FlowUIStatePathMarker()
]
FlowUIBlockId = Annotated[
    str, StringConstraints(min_length=1, max_length=64, pattern=BLOCK_ID_PATTERN)
]
FlowUIPageId = Annotated[
    str, StringConstraints(min_length=1, max_length=64, pattern=PAGE_ID_PATTERN)
]
FlowUIActionName = Annotated[
    str, StringConstraints(min_length=1, max_length=64, pattern=ACTION_NAME_PATTERN)
]
FlowUITone = Literal["neutral", "info", "success", "warning", "danger"]


def block_schema(group: FlowUIBlockGroup, icon: str) -> ConfigDict:
    """Метаданные палитры и инспектора; frontend читает их из JSON Schema."""

    return ConfigDict(json_schema_extra={"x-flow-ui-block": {"group": group, "icon": icon}})


class FlowUICondition(StrictBaseModel):
    """Условие показа блока: значение по пути равно ``equals``; без ``equals`` — истинно."""

    path: FlowUIStatePath
    equals: JsonValue = None


class FlowUIActionSpec(StrictBaseModel):
    """Действие интерактивного блока: имя и данные, уходящие во flow."""

    name: FlowUIActionName
    payload: JsonObject = Field(default_factory=dict)


class FlowUIBlockBase(StrictBaseModel):
    block_id: FlowUIBlockId
    visible_when: FlowUICondition | None = None


# --- Раскладка -----------------------------------------------------------------


class FlowUISection(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("layout", "square")

    type: Literal["section"] = "section"
    title: FlowUIText = ""
    blocks: list[FlowUIBlock] = Field(default_factory=list)


class FlowUIColumn(StrictBaseModel):
    width: int = Field(ge=1, le=12)
    blocks: list[FlowUIBlock] = Field(default_factory=list)


class FlowUIColumns(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("layout", "columns")

    type: Literal["columns"] = "columns"
    columns: list[FlowUIColumn] = Field(min_length=1, max_length=6)


class FlowUITab(StrictBaseModel):
    title: FlowUIText
    blocks: list[FlowUIBlock] = Field(default_factory=list)


class FlowUITabs(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("layout", "tabs")

    type: Literal["tabs"] = "tabs"
    tabs: list[FlowUITab] = Field(min_length=1, max_length=12)


# --- Контент -------------------------------------------------------------------


class FlowUIHeading(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "heading-1")

    type: Literal["heading"] = "heading"
    text: FlowUIText
    level: Literal[1, 2, 3] = 2


class FlowUIMarkdownText(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "text")

    type: Literal["text"] = "text"
    markdown: FlowUIText


class FlowUIImage(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "image")

    type: Literal["image"] = "image"
    url: FlowUIText
    alt: FlowUIText = ""


class FlowUIVideo(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "play")

    type: Literal["video"] = "video"
    url: FlowUIText


class FlowUIAudio(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "volume-up")

    type: Literal["audio"] = "audio"
    url: FlowUIText


class FlowUICode(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "code")

    type: Literal["code"] = "code"
    code: FlowUIText
    language: str = Field(default="text", max_length=32)


class FlowUIBadge(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "tag")

    type: Literal["badge"] = "badge"
    label: FlowUIText
    tone: FlowUITone = "neutral"


class FlowUIAlert(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "alert-triangle")

    type: Literal["alert"] = "alert"
    title: FlowUIText = ""
    message: FlowUIText
    tone: FlowUITone = "info"


class FlowUIMetric(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "chart")

    type: Literal["metric"] = "metric"
    label: FlowUIText
    value: FlowUIText
    hint: FlowUIText = ""


class FlowUIProgress(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "hourglass-top")

    type: Literal["progress"] = "progress"
    label: FlowUIText = ""
    value: FlowUIText = Field(description="Шаблон, дающий число от 0 до max")
    max: float = Field(default=100, gt=0)


class FlowUIStatus(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "fiber-manual-record")

    type: Literal["status"] = "status"
    label: FlowUIText
    tone: FlowUITone = "neutral"


class FlowUIEmptyState(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "inbox")

    type: Literal["empty_state"] = "empty_state"
    title: FlowUIText = ""
    message: FlowUIText


class FlowUIDivider(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("content", "minus")

    type: Literal["divider"] = "divider"


# --- Ввод ----------------------------------------------------------------------


class FlowUIInputBase(FlowUIBlockBase):
    """Общее для input-блоков: поле state, подпись, правила, действие при изменении."""

    field: FlowUIStatePath
    label: FlowUIText = ""
    required: bool = False
    error_message: FlowUIText = ""
    action: FlowUIActionSpec | None = None


class FlowUISelectOption(StrictBaseModel):
    value: str = Field(min_length=1, max_length=200)
    label: FlowUIText


class FlowUITextInput(FlowUIInputBase):
    model_config: ClassVar[ConfigDict] = block_schema("input", "text-fields")

    type: Literal["text_input"] = "text_input"
    placeholder: FlowUIText = ""
    default: FlowUIText = ""
    pattern: str = Field(default="", max_length=500)
    multiline: bool = False
    secret: bool = Field(default=False, description="Скрывать вводимые символы (пароль)")


class FlowUINumberInput(FlowUIInputBase):
    model_config: ClassVar[ConfigDict] = block_schema("input", "ruler")

    type: Literal["number_input"] = "number_input"
    placeholder: FlowUIText = ""
    default: float | None = None
    min: float | None = None
    max: float | None = None
    step: float = Field(default=1, gt=0)


class FlowUISelect(FlowUIInputBase):
    model_config: ClassVar[ConfigDict] = block_schema("input", "list")

    type: Literal["select"] = "select"
    placeholder: FlowUIText = ""
    options: list[FlowUISelectOption] = Field(min_length=1)
    multiple: bool = False
    default: str | list[str] | None = None


class FlowUICheckbox(FlowUIInputBase):
    model_config: ClassVar[ConfigDict] = block_schema("input", "check-square")

    type: Literal["checkbox"] = "checkbox"
    default: bool = False


class FlowUISwitch(FlowUIInputBase):
    model_config: ClassVar[ConfigDict] = block_schema("input", "swap-horiz")

    type: Literal["switch"] = "switch"
    default: bool = False


class FlowUISlider(FlowUIInputBase):
    model_config: ClassVar[ConfigDict] = block_schema("input", "adjustment")

    type: Literal["slider"] = "slider"
    min: float = 0
    max: float = 100
    step: float = Field(default=1, gt=0)
    default: float | None = None

    @model_validator(mode="after")
    def validate_range(self) -> FlowUISlider:
        if self.max <= self.min:
            raise ValueError(f"slider {self.block_id!r}: max must be greater than min")
        return self


class FlowUIDateInput(FlowUIInputBase):
    model_config: ClassVar[ConfigDict] = block_schema("input", "calendar")

    type: Literal["date_input"] = "date_input"
    default: FlowUIText = ""


class FlowUIDateTimeInput(FlowUIInputBase):
    model_config: ClassVar[ConfigDict] = block_schema("input", "schedule")

    type: Literal["datetime_input"] = "datetime_input"
    default: FlowUIText = ""


class FlowUIFileUpload(FlowUIInputBase):
    model_config: ClassVar[ConfigDict] = block_schema("input", "paperclip")

    type: Literal["file_upload"] = "file_upload"
    multiple: bool = True
    accept: str = Field(
        default="", max_length=500, description="accept-строка из реестра типов файлов"
    )


class FlowUIVoiceInput(FlowUIInputBase):
    model_config: ClassVar[ConfigDict] = block_schema("input", "mic")

    type: Literal["voice_input"] = "voice_input"
    placeholder: FlowUIText = ""


# --- Действия -------------------------------------------------------------------


class FlowUIButton(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("action", "zap")

    type: Literal["button"] = "button"
    label: FlowUIText
    action: FlowUIActionSpec
    variant: Literal["primary", "secondary", "ghost", "danger"] = "primary"


class FlowUILink(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("action", "link")

    type: Literal["link"] = "link"
    label: FlowUIText
    page_id: FlowUIPageId | None = None
    url: FlowUIText = ""

    @model_validator(mode="after")
    def validate_target(self) -> FlowUILink:
        if (self.page_id is None) == (self.url == ""):
            raise ValueError(f"link {self.block_id!r}: exactly one of page_id or url is required")
        return self


# --- Данные ---------------------------------------------------------------------


class FlowUITableColumn(StrictBaseModel):
    key: str = Field(min_length=1, max_length=64)
    label: FlowUIText


class FlowUIDataTable(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("data", "table")

    type: Literal["data_table"] = "data_table"
    rows: FlowUIStatePath | None = Field(default=None, description="Путь к списку строк в state")
    file_id: FlowUIText = Field(default="", description="Шаблон, дающий file_id табличного файла")
    columns: list[FlowUITableColumn] = Field(default_factory=list)
    row_action: FlowUIActionSpec | None = None

    @model_validator(mode="after")
    def validate_source(self) -> FlowUIDataTable:
        if (self.rows is None) == (self.file_id == ""):
            raise ValueError(
                f"data_table {self.block_id!r}: exactly one of rows or file_id is required"
            )
        return self


class FlowUIChart(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("data", "chart")

    type: Literal["chart"] = "chart"
    kind: Literal["bar", "line", "area", "pie"] = "bar"
    title: FlowUIText = ""
    data: FlowUIStatePath = Field(description="Путь к списку точек (объектов) в state")
    x: str = Field(min_length=1, max_length=64)
    y: list[str] = Field(min_length=1, max_length=8)


class FlowUIJsonView(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("data", "trace-json")

    type: Literal["json_view"] = "json_view"
    path: FlowUIStatePath
    title: FlowUIText = ""


class FlowUIFileCard(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("data", "file-text")

    type: Literal["file_card"] = "file_card"
    file: FlowUIStatePath | None = Field(default=None, description="Путь к FileRef в state")
    file_id: FlowUIText = Field(default="", description="Шаблон, дающий file_id из state.files")

    @model_validator(mode="after")
    def validate_source(self) -> FlowUIFileCard:
        if (self.file is None) == (self.file_id == ""):
            raise ValueError(
                f"file_card {self.block_id!r}: exactly one of file or file_id is required"
            )
        return self


class FlowUIFileList(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("data", "folder")

    type: Literal["file_list"] = "file_list"
    files: FlowUIStatePath = Field(default="files", description="Путь к списку FileRef в state")


# --- Платформа ------------------------------------------------------------------


class FlowUIConversationSettings(StrictBaseModel):
    """Настройки ленты и композера; ими владеет блок conversation."""

    greeting: FlowUIText = ""
    suggested_prompts: list[FlowUIText] = Field(default_factory=list, max_length=12)
    placeholder: FlowUIText = ""
    show_reasoning: bool = False
    tool_calls: Literal["hidden", "compact", "detailed"] = "compact"
    show_activity: bool = True
    show_skill_loads: bool = True
    show_reflection: bool = True
    errors: Literal["generic", "detailed"] = "generic"
    show_run_trace: bool = False
    show_trace_actions: bool = False
    show_browser_previews: bool = True
    show_files_panel: bool = True
    allow_cancel: bool = True
    allow_voice: bool = True


class FlowUIConversation(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("platform", "chat")

    type: Literal["conversation"] = "conversation"
    settings: FlowUIConversationSettings = Field(default_factory=FlowUIConversationSettings)


class FlowUISlot(FlowUIBlockBase):
    """Цель ``ui_render``: сюда агент кладёт блоки во время выполнения."""

    model_config: ClassVar[ConfigDict] = block_schema("platform", "box")

    type: Literal["slot"] = "slot"
    title: FlowUIText = ""


class FlowUIAgentIdentity(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("platform", "bot")

    type: Literal["agent_identity"] = "agent_identity"
    title: FlowUIText = ""
    image_url: str = Field(default="", max_length=2000)


class FlowUIAvatar(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("platform", "avatar")

    type: Literal["avatar"] = "avatar"
    name: FlowUIText
    image_url: FlowUIText = ""


class FlowUIRunTrace(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("platform", "trace-tree")

    type: Literal["run_trace"] = "run_trace"


class FlowUIToolActivity(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("platform", "tool")

    type: Literal["tool_activity"] = "tool_activity"
    display: Literal["compact", "detailed"] = "compact"


class FlowUIBrowserPreview(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("platform", "globe")

    type: Literal["browser_preview"] = "browser_preview"
    url: FlowUIText
    title: FlowUIText = ""
    screenshot_url: FlowUIText = ""
    status: Literal["running", "finished", "failed"] = "finished"


class FlowUISkillActivity(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("platform", "sparkle")

    type: Literal["skill_activity"] = "skill_activity"
    agent_skill_id: str = Field(min_length=1, max_length=128)
    title: FlowUIText
    status: Literal["loading", "loaded", "failed"] = "loaded"


class FlowUIActionPreview(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("platform", "eye")

    type: Literal["action_preview"] = "action_preview"
    title: FlowUIText
    summary: FlowUIText = ""
    parameters: JsonObject = Field(default_factory=dict)


class FlowUIActionResult(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("platform", "done-all")

    type: Literal["action_result"] = "action_result"
    title: FlowUIText
    status: Literal["success", "failed", "pending"] = "success"
    summary: FlowUIText = ""


class FlowUIReflection(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("platform", "quote")

    type: Literal["reflection"] = "reflection"
    text: FlowUIText


class FlowUIActivity(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("platform", "refresh")

    type: Literal["activity"] = "activity"
    title: FlowUIText
    status: Literal["running", "completed", "failed"] = "running"
    detail: FlowUIText = ""


class FlowUISuggestedPrompts(FlowUIBlockBase):
    model_config: ClassVar[ConfigDict] = block_schema("platform", "list-check")

    type: Literal["suggested_prompts"] = "suggested_prompts"
    items: list[FlowUIText] = Field(min_length=1, max_length=12)


# --- Свой код ---------------------------------------------------------------------


class FlowUIHtml(FlowUIBlockBase):
    """Пользовательский HTML/CSS/JS в sandbox-iframe с opaque origin.

    Код получает проекцию state по ``fields`` и путям ``data-bind``/``data-show``
    из ``source``; пишет значение в ``field`` через ``flowUi.setValue``.
    """

    model_config: ClassVar[ConfigDict] = block_schema("custom", "terminal")

    type: Literal["html"] = "html"
    source: str = Field(min_length=1)
    height: int | Literal["auto"] = Field(default="auto")
    fields: list[FlowUIStatePath] = Field(default_factory=list, max_length=64)
    field: FlowUIStatePath | None = None

    @model_validator(mode="after")
    def validate_height(self) -> FlowUIHtml:
        if isinstance(self.height, int) and not 24 <= self.height <= 4000:
            raise ValueError(f"html {self.block_id!r}: height must be between 24 and 4000 px")
        return self


FlowUIInputBlock = (
    FlowUITextInput
    | FlowUINumberInput
    | FlowUISelect
    | FlowUICheckbox
    | FlowUISwitch
    | FlowUISlider
    | FlowUIDateInput
    | FlowUIDateTimeInput
    | FlowUIFileUpload
    | FlowUIVoiceInput
)

FlowUIBlock = Annotated[
    FlowUISection
    | FlowUIColumns
    | FlowUITabs
    | FlowUIHeading
    | FlowUIMarkdownText
    | FlowUIImage
    | FlowUIVideo
    | FlowUIAudio
    | FlowUICode
    | FlowUIBadge
    | FlowUIAlert
    | FlowUIMetric
    | FlowUIProgress
    | FlowUIStatus
    | FlowUIEmptyState
    | FlowUIDivider
    | FlowUITextInput
    | FlowUINumberInput
    | FlowUISelect
    | FlowUICheckbox
    | FlowUISwitch
    | FlowUISlider
    | FlowUIDateInput
    | FlowUIDateTimeInput
    | FlowUIFileUpload
    | FlowUIVoiceInput
    | FlowUIButton
    | FlowUILink
    | FlowUIDataTable
    | FlowUIChart
    | FlowUIJsonView
    | FlowUIFileCard
    | FlowUIFileList
    | FlowUIConversation
    | FlowUISlot
    | FlowUIAgentIdentity
    | FlowUIAvatar
    | FlowUIRunTrace
    | FlowUIToolActivity
    | FlowUIBrowserPreview
    | FlowUISkillActivity
    | FlowUIActionPreview
    | FlowUIActionResult
    | FlowUIReflection
    | FlowUIActivity
    | FlowUISuggestedPrompts
    | FlowUIHtml,
    Field(discriminator="type"),
]

FlowUIBlockModel = (
    FlowUISection
    | FlowUIColumns
    | FlowUITabs
    | FlowUIHeading
    | FlowUIMarkdownText
    | FlowUIImage
    | FlowUIVideo
    | FlowUIAudio
    | FlowUICode
    | FlowUIBadge
    | FlowUIAlert
    | FlowUIMetric
    | FlowUIProgress
    | FlowUIStatus
    | FlowUIEmptyState
    | FlowUIDivider
    | FlowUIInputBlock
    | FlowUIButton
    | FlowUILink
    | FlowUIDataTable
    | FlowUIChart
    | FlowUIJsonView
    | FlowUIFileCard
    | FlowUIFileList
    | FlowUIConversation
    | FlowUISlot
    | FlowUIAgentIdentity
    | FlowUIAvatar
    | FlowUIRunTrace
    | FlowUIToolActivity
    | FlowUIBrowserPreview
    | FlowUISkillActivity
    | FlowUIActionPreview
    | FlowUIActionResult
    | FlowUIReflection
    | FlowUIActivity
    | FlowUISuggestedPrompts
    | FlowUIHtml
)

FlowUIRenderTarget = FlowUISlot | FlowUIConversation

INPUT_BLOCK_TYPES: frozenset[str] = frozenset(
    {
        "text_input",
        "number_input",
        "select",
        "checkbox",
        "switch",
        "slider",
        "date_input",
        "datetime_input",
        "file_upload",
        "voice_input",
    }
)


def iter_blocks(blocks: list[FlowUIBlockModel]) -> list[FlowUIBlockModel]:
    """Все блоки дерева в порядке обхода в глубину, включая контейнеры."""

    ordered: list[FlowUIBlockModel] = []
    for block in blocks:
        ordered.append(block)
        if isinstance(block, FlowUISection):
            ordered.extend(iter_blocks(block.blocks))
        elif isinstance(block, FlowUIColumns):
            for column in block.columns:
                ordered.extend(iter_blocks(column.blocks))
        elif isinstance(block, FlowUITabs):
            for tab in block.tabs:
                ordered.extend(iter_blocks(tab.blocks))
    return ordered


def input_field_type_name(block: FlowUIInputBlock) -> str:
    """Тип значения, которое input-блок записывает в ``state[field]`` (для инспектора dataflow)."""
    if isinstance(block, FlowUINumberInput | FlowUISlider):
        return "number"
    if isinstance(block, FlowUICheckbox | FlowUISwitch):
        return "boolean"
    if isinstance(block, FlowUISelect):
        return "array" if block.multiple else "string"
    if isinstance(block, FlowUIFileUpload):
        return "array"
    return "string"


def assert_unique_block_ids(blocks: list[FlowUIBlockModel], *, scope: str) -> None:
    seen: set[str] = set()
    for block in iter_blocks(blocks):
        if block.block_id in seen:
            raise ValueError(f"{scope}: duplicate block_id {block.block_id!r}")
        seen.add(block.block_id)


class FlowUIPage(StrictBaseModel):
    page_id: FlowUIPageId
    title: FlowUIText = ""
    blocks: list[FlowUIBlock] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_blocks(self) -> FlowUIPage:
        assert_unique_block_ids(self.blocks, scope=f"page {self.page_id!r}")
        return self

    def render_target_ids(self) -> list[str]:
        return [
            block.block_id
            for block in iter_blocks(self.blocks)
            if isinstance(block, FlowUISlot | FlowUIConversation)
        ]


class FlowUIDocument(StrictBaseModel):
    """Design-time интерфейс flow: страницы с блоками и стартовая страница."""

    pages: list[FlowUIPage] = Field(min_length=1, max_length=100)
    start_page_id: FlowUIPageId

    @model_validator(mode="after")
    def validate_pages(self) -> FlowUIDocument:
        page_ids = [page.page_id for page in self.pages]
        if len(set(page_ids)) != len(page_ids):
            raise ValueError("Flow UI document: duplicate page_id")
        if self.start_page_id not in page_ids:
            raise ValueError(
                f"Flow UI document: start_page_id {self.start_page_id!r} is not a page"
            )
        return self

    def page(self, page_id: str) -> FlowUIPage:
        for page in self.pages:
            if page.page_id == page_id:
                return page
        raise KeyError(f"Flow UI document has no page {page_id!r}")

    def blocks(self) -> list[FlowUIBlockModel]:
        collected: list[FlowUIBlockModel] = []
        for page in self.pages:
            collected.extend(iter_blocks(page.blocks))
        return collected

    def input_blocks(self) -> list[FlowUIInputBlock]:
        return [block for block in self.blocks() if isinstance(block, FlowUIInputBase)]

    def conversation_settings(self) -> FlowUIConversationSettings:
        """Настройки первого блока conversation; без ленты действуют настройки по умолчанию."""
        for block in self.blocks():
            if isinstance(block, FlowUIConversation):
                return block.settings
        return FlowUIConversationSettings()

    def agent_identity_image_url(self) -> str | None:
        for block in self.blocks():
            if isinstance(block, FlowUIAgentIdentity) and block.image_url != "":
                return block.image_url
        return None

    def with_embed_overrides(
        self,
        *,
        conversation: FlowUIConversationSettings | None,
        start_page_id: FlowUIPageId | None,
    ) -> FlowUIDocument:
        """Документ для embed-поверхности: настройки всех лент и стартовая страница из EmbedConfig."""
        pages = self.pages
        if conversation is not None:
            pages = [
                page.model_copy(
                    update={"blocks": _with_conversation_settings(page.blocks, conversation)}
                )
                for page in pages
            ]
        return FlowUIDocument(
            pages=pages,
            start_page_id=self.start_page_id if start_page_id is None else start_page_id,
        )


def _with_conversation_settings(
    blocks: list[FlowUIBlockModel],
    settings: FlowUIConversationSettings,
) -> list[FlowUIBlockModel]:
    rebuilt: list[FlowUIBlockModel] = []
    for block in blocks:
        if isinstance(block, FlowUIConversation):
            rebuilt.append(block.model_copy(update={"settings": settings}))
        elif isinstance(block, FlowUISection):
            rebuilt.append(
                block.model_copy(
                    update={"blocks": _with_conversation_settings(block.blocks, settings)}
                )
            )
        elif isinstance(block, FlowUIColumns):
            columns = [
                column.model_copy(
                    update={"blocks": _with_conversation_settings(column.blocks, settings)}
                )
                for column in block.columns
            ]
            rebuilt.append(block.model_copy(update={"columns": columns}))
        elif isinstance(block, FlowUITabs):
            tabs = [
                tab.model_copy(update={"blocks": _with_conversation_settings(tab.blocks, settings)})
                for tab in block.tabs
            ]
            rebuilt.append(block.model_copy(update={"tabs": tabs}))
        else:
            rebuilt.append(block)
    return rebuilt


for _model in FlowUISection, FlowUIColumn, FlowUITab, FlowUIPage:
    _ = _model.model_rebuild()


__all__ = [
    "ACTION_NAME_PATTERN",
    "BLOCK_ID_PATTERN",
    "INPUT_BLOCK_TYPES",
    "PAGE_ID_PATTERN",
    "STATE_PATH_PATTERN",
    "FlowUIActionName",
    "FlowUIActionPreview",
    "FlowUIActionResult",
    "FlowUIActionSpec",
    "FlowUIActivity",
    "FlowUIAgentIdentity",
    "FlowUIAlert",
    "FlowUIAudio",
    "FlowUIAvatar",
    "FlowUIBadge",
    "FlowUIBlock",
    "FlowUIBlockBase",
    "FlowUIBlockGroup",
    "FlowUIBlockId",
    "FlowUIBlockModel",
    "FlowUIBrowserPreview",
    "FlowUIButton",
    "FlowUIChart",
    "FlowUICheckbox",
    "FlowUICode",
    "FlowUIColumn",
    "FlowUIColumns",
    "FlowUICondition",
    "FlowUIConversation",
    "FlowUIConversationSettings",
    "FlowUIDataTable",
    "FlowUIDateInput",
    "FlowUIDateTimeInput",
    "FlowUIDivider",
    "FlowUIDocument",
    "FlowUIEmptyState",
    "FlowUIFileCard",
    "FlowUIFileList",
    "FlowUIFileUpload",
    "FlowUIHeading",
    "FlowUIHtml",
    "FlowUIImage",
    "FlowUIInputBase",
    "FlowUIInputBlock",
    "FlowUIJsonView",
    "FlowUILink",
    "FlowUIMarkdownText",
    "FlowUIMetric",
    "FlowUINumberInput",
    "FlowUIPage",
    "FlowUIPageId",
    "FlowUIProgress",
    "FlowUIReflection",
    "FlowUIRenderTarget",
    "FlowUIRunTrace",
    "FlowUISection",
    "FlowUISelect",
    "FlowUISelectOption",
    "FlowUISkillActivity",
    "FlowUISlider",
    "FlowUISlot",
    "FlowUIStatePath",
    "FlowUIStatePathMarker",
    "FlowUIStatus",
    "FlowUISuggestedPrompts",
    "FlowUISwitch",
    "FlowUITab",
    "FlowUITableColumn",
    "FlowUITabs",
    "FlowUITemplateText",
    "FlowUIText",
    "FlowUITextInput",
    "FlowUITone",
    "FlowUIToolActivity",
    "FlowUIVideo",
    "FlowUIVoiceInput",
    "assert_unique_block_ids",
    "block_schema",
    "input_field_type_name",
    "iter_blocks",
]
