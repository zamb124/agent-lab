"""
Pydantic-модели BFF office.
"""

from datetime import datetime
from typing import List, Literal, Self

from pydantic import BaseModel, Field, model_validator


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


class OfficeDocumentListResponse(BaseModel):
    items: List[OfficeDocumentItem]


class OfficeDocumentCreateResponse(BaseModel):
    binding_id: str
    file_id: str
    catalog_id: str


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


class OfficeNamespaceItem(BaseModel):
    """Рабочее пространство компании; данные из shared storage (`NamespaceRepository`)."""

    name: str
    is_default: bool = False


class OfficeNamespacesResponse(BaseModel):
    items: List[OfficeNamespaceItem]


class OfficeNamespaceTemplateItem(BaseModel):
    """Шаблон пространства (ответ CRM), для модалки создания namespace."""

    template_id: str
    name: str
    description: str | None = None
    icon: str | None = None
    is_system: bool = False
    entity_type_ids: List[str] = Field(default_factory=list)


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


class OfficeCatalogListResponse(BaseModel):
    items: List[OfficeCatalogListItem]


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
    members: List[OfficeCatalogMemberItem]
