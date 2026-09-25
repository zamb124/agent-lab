"""
Pydantic-модели BFF office.
"""

from datetime import datetime
from typing import ClassVar, Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.documents.viewer.models import DocumentOpenConfigResponse
from core.pagination import ListResponse
from core.rag.models import RAGNamespaceSearchRequest, RAGSearchOptions

SpreadsheetCellValue: TypeAlias = str | int | float | bool | None


OfficeDocumentRagIndexStatus: TypeAlias = Literal["ready", "pending", "failed", "absent"]


class OfficeDocumentItem(BaseModel):
    file_id: str
    catalog_id: str
    title: str
    file_category: str
    onlyoffice_document_type: str | None = None
    file_availability: Literal["available", "missing"] = "available"
    file_expires_at: datetime | None = None
    file_size: int
    created_at: datetime
    updated_at: datetime
    created_by_user_id: str
    created_by_display_name: str
    created_by_avatar_url: str | None = None
    rag_index_status: OfficeDocumentRagIndexStatus | None = None


OfficeDocumentListResponse = ListResponse[OfficeDocumentItem]


class OfficeDocumentsRagIndexStatusesRequest(BaseModel):
    file_ids: list[str] = Field(..., min_length=1, max_length=500)


class OfficeDocumentsRagIndexStatusesResponse(BaseModel):
    statuses: dict[str, OfficeDocumentRagIndexStatus]


class OfficeDocumentCreateResponse(BaseModel):
    file_id: str
    catalog_id: str
    file_category: str | None = None
    onlyoffice_document_type: str | None = None
    title: str | None = None
    editor_url: str | None = None


class OfficeDocumentFromFileRequest(BaseModel):
    file_id: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    catalog_id: str | None = None


class OfficeDocumentEditorSessionResponse(BaseModel):
    file_id: str
    catalog_id: str
    title: str
    file_category: str
    onlyoffice_document_type: str | None = None
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
    catalog_id: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def spreadsheet_format_only_for_cell(self) -> Self:
        if self.document_type != "cell":
            if self.spreadsheet_format is not None:
                raise ValueError("spreadsheet_format is allowed only when document_type=cell")
            return self
        if self.spreadsheet_format is None:
            self.spreadsheet_format = "xlsx"
        return self


class OfficeDocumentRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)


class OfficeDocumentRenameResponse(BaseModel):
    file_id: str
    title: str


class OfficeDocumentMoveRequest(BaseModel):
    catalog_id: str = Field(min_length=1, max_length=64)


class OfficeDocumentCopyRequest(BaseModel):
    catalog_id: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=500)


class OfficeDocumentShareCreateRequest(BaseModel):
    permission: Literal["viewer", "editor"] = "viewer"
    expires_in_hours: int | None = Field(default=None, ge=1, le=8760)


class OfficeDocumentShareItem(BaseModel):
    share_id: str
    file_id: str
    permission: str
    share_url: str | None = None
    expires_at: datetime | None = None
    created_at: datetime


class OfficeDocumentShareResolveResponse(BaseModel):
    file_id: str
    title: str
    permission: str
    file_category: str
    onlyoffice_document_type: str | None = None


class OfficeDocumentPreviewResponse(BaseModel):
    file_id: str
    preview_url: str | None = None
    editor_mode: Literal["view"] = "view"


class OfficeDocumentAiSummaryResponse(BaseModel):
    file_id: str
    summary: str
    enabled: bool


class OfficeDocumentMetadataResponse(BaseModel):
    file_id: str
    classification_label: str | None = None
    retention_days: int | None = None


class OfficeIntegrationStatusResponse(BaseModel):
    configured: bool
    detail: str = ""


OfficeEditorConfigResponse = DocumentOpenConfigResponse


class OnlyOfficeCallbackResponse(BaseModel):
    error: int = 0


class OnlyOfficeDownloadTokenClaims(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    typ: Literal["office_dl"]
    viewer_scope: Literal["catalog", "file"]
    file_id: str
    company_id: str
    iat: int
    exp: int


class OnlyOfficeCallbackContextClaims(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    typ: Literal["office_cb"]
    viewer_scope: Literal["catalog", "file"]
    file_id: str
    company_id: str
    iat: int
    exp: int
    namespace: str | None = None

    @model_validator(mode="after")
    def namespace_required_for_catalog_scope(self) -> Self:
        if self.viewer_scope == "catalog" and (self.namespace is None or self.namespace == ""):
            raise ValueError("namespace is required for a catalog callback token")
        return self


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
    company_visible: bool = True
    parent_catalog_id: str | None = Field(default=None, max_length=64)


class OfficeCatalogPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    company_visible: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if self.title is None and self.company_visible is None:
            raise ValueError("Specify title and/or company_visible")
        return self


class OfficeCatalogListItem(BaseModel):
    catalog_id: str
    parent_catalog_id: str | None = None
    title: str
    file_count: int
    owner_user_id: str
    owner_display_name: str
    owner_avatar_url: str | None = None
    is_owner: bool
    company_visible: bool
    rag_index_enabled: bool
    rag_index_include_subcatalogs: bool
    rag_index_search_options: RAGSearchOptions | None = None


OfficeCatalogListResponse = ListResponse[OfficeCatalogListItem]


class OfficeCatalogItemsResponse(BaseModel):
    catalog_id: str
    catalogs: list[OfficeCatalogListItem]
    documents: list[OfficeDocumentItem]


class OfficeCatalogDetailResponse(BaseModel):
    catalog_id: str
    parent_catalog_id: str | None = None
    title: str
    owner_user_id: str
    owner_display_name: str
    owner_avatar_url: str | None = None
    is_owner: bool
    company_visible: bool


OfficeAccessMemberRelation = Literal["viewer", "editor"]


class OfficeCatalogMemberAddRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    relation: OfficeAccessMemberRelation = "viewer"


class OfficeCatalogMemberItem(BaseModel):
    user_id: str
    display_name: str
    avatar_url: str | None = None
    relation: OfficeAccessMemberRelation = "viewer"


class OfficeCatalogRagIndexStatusTotals(BaseModel):
    ready: int = 0
    pending: int = 0
    failed: int = 0
    absent: int = 0


class OfficeCatalogRagIndexEnableResponse(BaseModel):
    rag_namespace_id: str
    initial_task_id: str | None = None


class OfficeCatalogRagIndexDisableResponse(BaseModel):
    success: bool = True


class OfficeCatalogRagIndexRebuildResponse(BaseModel):
    task_id: str | None = None
    enqueued_documents: int = 0


class OfficeCatalogRagIndexStatusResponse(BaseModel):
    enabled: bool
    rag_namespace_id: str
    include_subcatalogs: bool
    search_options: RAGSearchOptions | None = None
    platform_defaults: RAGSearchOptions
    totals: OfficeCatalogRagIndexStatusTotals
    rag_index_updated_at: datetime | None = None


class OfficeCatalogRagIndexSettingsPatchRequest(RAGSearchOptions):
    include_subcatalogs: bool | None = None
    clear_search_options: bool | None = None

    @model_validator(mode="after")
    def patch_must_include_at_least_one_field(self) -> "OfficeCatalogRagIndexSettingsPatchRequest":
        has_include = self.include_subcatalogs is not None
        has_clear = self.clear_search_options is True
        has_search_options = any(
            getattr(self, field_name) is not None
            for field_name in RAGSearchOptions.model_fields
        )
        if not has_include and not has_clear and not has_search_options:
            raise ValueError(
                "patch must contain include_subcatalogs, clear_search_options "
                + "or at least one search_options field"
            )
        return self


class OfficeCatalogRagIndexSettingsResponse(BaseModel):
    include_subcatalogs: bool
    search_options: RAGSearchOptions | None = None


class OfficeCatalogSemanticSearchRequest(RAGNamespaceSearchRequest):
    limit: int = Field(default=20, ge=1, le=50)


class OfficeCatalogSemanticSearchHit(BaseModel):
    file_id: str
    catalog_id: str
    catalog_title: str
    title: str
    snippet: str
    score: float


class OfficeCatalogSemanticSearchResponse(BaseModel):
    query: str
    include_subcatalogs: bool
    catalog_ids: list[str]
    items: list[OfficeCatalogSemanticSearchHit]


class OfficeCatalogMembersResponse(BaseModel):
    members: list[OfficeCatalogMemberItem]


OfficeLinkPermission = Literal["viewer", "editor"]
OfficeAccessResourceKind = Literal["catalog", "binding"]


class OfficeResourceAccessMemberItem(BaseModel):
    user_id: str
    relation: OfficeAccessMemberRelation = "viewer"


class OfficeResourceAccessResponse(BaseModel):
    resource_kind: OfficeAccessResourceKind
    resource_id: str
    company_visible: bool
    link_enabled: bool
    link_permission: OfficeLinkPermission
    public_url: str | None = None
    members: list[OfficeResourceAccessMemberItem]


class OfficeResourceAccessPatchRequest(BaseModel):
    company_visible: bool | None = None
    link_enabled: bool | None = None
    link_permission: OfficeLinkPermission | None = None
    members: list[OfficeResourceAccessMemberItem] | None = None


class OfficeResourceAccessRotateLinkResponse(BaseModel):
    public_url: str


class OfficePublicResolveResponse(BaseModel):
    resource_kind: OfficeAccessResourceKind
    resource_id: str
    title: str
    link_permission: OfficeLinkPermission
    file_id: str | None = None
    catalog_id: str | None = None


class OfficePublicCatalogItem(BaseModel):
    title: str
    file_id: str
    file_category: str
    onlyoffice_document_type: str | None = None
    link_permission: OfficeLinkPermission


class OfficePublicCatalogItemsResponse(BaseModel):
    catalog_id: str
    title: str
    items: list[OfficePublicCatalogItem]
