"""
Pydantic-модели BFF office.
"""

from datetime import datetime
from typing import ClassVar, Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.pagination import ListResponse

SpreadsheetCellValue: TypeAlias = str | int | float | bool | None


class OfficeDocumentItem(BaseModel):
    binding_id: str
    catalog_id: str
    title: str
    file_id: str
    document_type: str
    created_at: datetime
    created_by_user_id: str
    created_by_display_name: str
    created_by_avatar_url: str | None = None


OfficeDocumentListResponse = ListResponse[OfficeDocumentItem]


class OfficeDocumentCreateResponse(BaseModel):
    binding_id: str
    file_id: str
    catalog_id: str
    document_type: str | None = None
    title: str | None = None
    editor_url: str | None = None


class OfficeDocumentFromFileRequest(BaseModel):
    file_id: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    catalog_id: str | None = None


class OfficeDocumentEditorSessionResponse(BaseModel):
    binding_id: str
    file_id: str
    catalog_id: str
    title: str
    document_type: str
    namespace: str
    editor_url: str


class OfficeDocumentSyncRequest(BaseModel):
    close: bool = False
    settle_ms: int = Field(default=750, ge=0, le=3000)
    dirty: bool | None = None


class OfficeFileEditorSyncResponse(BaseModel):
    file_id: str
    checksum: str | None = None
    file_size: int


class OfficeDocumentMutationResponse(BaseModel):
    binding_id: str
    file_id: str
    checksum: str | None = None
    file_size: int
    editor_url: str
    changed_count: int | None = None


class OfficeDocumentReplaceTextRequest(BaseModel):
    find: str = Field(min_length=1, max_length=2000)
    replace: str = Field(default="", max_length=20000)
    match_case: bool = False
    tool_call_id: str | None = Field(default=None, max_length=128)


class OfficeDocumentAppendTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200000)
    tool_call_id: str | None = Field(default=None, max_length=128)


class OfficeSpreadsheetUpdateCellsRequest(BaseModel):
    cells: dict[str, SpreadsheetCellValue] = Field(min_length=1)
    sheet: str | None = Field(default=None, max_length=128)
    tool_call_id: str | None = Field(default=None, max_length=128)


class OfficeEmptyCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    document_type: Literal["word", "cell", "slide"] = "word"
    spreadsheet_format: Literal["xlsx", "csv"] | None = None
    catalog_id: str | None = None

    @model_validator(mode="after")
    def spreadsheet_format_only_for_cell(self) -> Self:
        if self.document_type != "cell":
            if self.spreadsheet_format is not None:
                raise ValueError("spreadsheet_format допустим только при document_type=cell")
            return self
        if self.spreadsheet_format is None:
            self.spreadsheet_format = "xlsx"
        return self


class OfficeDocumentRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)


class OfficeDocumentRenameResponse(BaseModel):
    binding_id: str
    title: str


class OfficeIntegrationStatusResponse(BaseModel):
    configured: bool
    detail: str = ""


class OfficeEditorConfigResponse(BaseModel):
    document_server_url: str
    token: str


class OnlyOfficeCallbackResponse(BaseModel):
    error: int = 0


class OnlyOfficeDownloadTokenClaims(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    typ: Literal["office_dl"]
    binding_kind: Literal["document", "file"]
    file_id: str
    company_id: str
    binding_id: str
    iat: int
    exp: int


class OnlyOfficeCallbackContextClaims(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    typ: Literal["office_cb"]
    binding_kind: Literal["document", "file"]
    binding_id: str
    company_id: str
    iat: int
    exp: int
    namespace: str | None = None
    file_id: str | None = None

    @model_validator(mode="after")
    def required_binding_fields(self) -> Self:
        if self.binding_kind == "document":
            if self.namespace is None or self.namespace == "":
                raise ValueError("namespace обязателен для document callback-токена")
            return self
        if self.file_id is None or self.file_id == "":
            raise ValueError("file_id обязателен для file callback-токена")
        return self


class OfficeNamespaceItem(BaseModel):
    """Рабочее пространство компании; данные из shared storage (`NamespaceRepository`)."""

    name: str
    is_default: bool = False


class OfficeNamespaceTemplateItem(BaseModel):
    """Шаблон пространства (ответ CRM), для модалки создания namespace."""

    template_id: str
    name: str
    description: str | None = None
    icon: str | None = None
    is_system: bool = False
    entity_type_ids: list[str] = Field(default_factory=list)


class OfficeNamespaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    template_id: str = Field(min_length=1, max_length=128)


class OfficeNamespaceCreateResponse(BaseModel):
    name: str
    company_id: str
    description: str | None = None
    is_default: bool = False


class OfficeCatalogCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    is_public: bool = True


class OfficeCatalogPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    is_public: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if self.title is None and self.is_public is None:
            raise ValueError("Укажите title и/или is_public")
        return self


class OfficeCatalogListItem(BaseModel):
    catalog_id: str
    title: str
    file_count: int
    owner_user_id: str
    owner_display_name: str
    owner_avatar_url: str | None = None
    is_owner: bool
    is_public: bool


OfficeCatalogListResponse = ListResponse[OfficeCatalogListItem]


class OfficeCatalogDetailResponse(BaseModel):
    catalog_id: str
    title: str
    owner_user_id: str
    owner_display_name: str
    owner_avatar_url: str | None = None
    is_owner: bool
    is_public: bool


class OfficeCatalogMemberAddRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)


class OfficeCatalogMemberItem(BaseModel):
    user_id: str
    display_name: str
    avatar_url: str | None = None


class OfficeCatalogMembersResponse(BaseModel):
    members: list[OfficeCatalogMemberItem]
