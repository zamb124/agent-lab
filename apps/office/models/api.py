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
    namespaces: List[OfficeNamespaceItem]


class OfficeCatalogCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)


class OfficeCatalogPatchRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)


class OfficeCatalogListItem(BaseModel):
    catalog_id: str
    title: str
    file_count: int
    owner_user_id: str
    owner_display_name: str
    owner_avatar_url: str | None = None
    is_owner: bool


class OfficeCatalogListResponse(BaseModel):
    items: List[OfficeCatalogListItem]


class OfficeCatalogDetailResponse(BaseModel):
    catalog_id: str
    title: str
    owner_user_id: str
    owner_display_name: str
    owner_avatar_url: str | None = None
    is_owner: bool


class OfficeCatalogMemberAddRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)


class OfficeCatalogMemberItem(BaseModel):
    user_id: str
    display_name: str
    avatar_url: str | None = None


class OfficeCatalogMembersResponse(BaseModel):
    members: List[OfficeCatalogMemberItem]
