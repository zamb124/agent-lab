"""Pydantic input models for Documents REST client and Flows tools."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.files.reader.models import MAX_READ_BUDGET

DocumentType = Literal["word", "cell", "slide"]
SpreadsheetFormat = Literal["xlsx", "csv"]
FindMode = Literal["auto", "semantic", "lexical"]
LinkKind = Literal["editor", "preview"]
AccessResourceKind = Literal["catalog", "document"]
LinkPermission = Literal["view", "edit"]
CellValue = str | int | float | bool | None


class DocumentsEmptyArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class DocumentsOpenFileArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str | None = Field(
        None,
        description="ID файла из state.files[].file_id. Используй его, если он известен.",
    )
    file_name: str | None = Field(
        None,
        description="Имя файла из state.files[].original_name; используется, если file_id не передан.",
    )
    title: str | None = Field(
        None,
        description="Название документа в сервисе documents; если не передано, берётся имя файла.",
    )
    catalog_id: str | None = Field(
        None,
        description="Каталог documents. Не передавай, если пользователь явно не выбрал каталог.",
    )

    @model_validator(mode="after")
    def _require_file_ref(self) -> DocumentsOpenFileArgs:
        if not self.file_id and not self.file_name:
            raise ValueError("file_id or file_name is required")
        return self


class DocumentsFromFileArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="Platform file_id to bind into Documents.")
    title: str | None = Field(None, description="Optional Documents title.")
    catalog_id: str | None = Field(None, description="Optional target catalog_id.")


class DocumentsReplaceTextArgs(DocumentsOpenFileArgs):
    find: str = Field(..., min_length=1, description="Точный текст, который надо заменить.")
    replace: str = Field("", description="Текст замены.")
    match_case: bool = Field(False, description="Учитывать регистр при поиске.")


class DocumentsAppendTextArgs(DocumentsOpenFileArgs):
    text: str = Field(..., min_length=1, description="Текст, который нужно добавить в конец документа.")


class DocumentsUpdateCellsArgs(DocumentsOpenFileArgs):
    cells: dict[str, CellValue] = Field(
        ...,
        min_length=1,
        description='Карта Excel/CSV ячеек: {"A1": "value", "B2": 10}.',
    )
    sheet: str | None = Field(None, description="Название листа; null — активный лист.")


class DocumentsReplaceTextMutationArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="Documents binding file_id.")
    find: str = Field(..., min_length=1, description="Exact text to replace.")
    replace: str = Field("", description="Replacement text.")
    match_case: bool = Field(False, description="Case-sensitive match.")
    tool_call_id: str | None = Field(None, description="Optional active tool_call_id.")


class DocumentsAppendTextMutationArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="Documents binding file_id.")
    text: str = Field(..., min_length=1, description="Text to append.")
    tool_call_id: str | None = Field(None, description="Optional active tool_call_id.")


class DocumentsUpdateCellsMutationArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="Documents binding file_id.")
    cells: dict[str, CellValue] = Field(..., min_length=1, description="Cell address → value map.")
    sheet: str | None = Field(None, description="Sheet name; null = active sheet.")
    tool_call_id: str | None = Field(None, description="Optional active tool_call_id.")


class DocumentsCreateEmptyArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=500, description="Title of the new blank document.")
    document_type: DocumentType = Field(
        "word",
        description="Blank Office kind: word (.docx), cell (.xlsx/.csv), slide (.pptx).",
    )
    catalog_id: str = Field(
        ...,
        min_length=1,
        description="Target catalog_id. Required when the namespace has catalogs.",
    )
    spreadsheet_format: SpreadsheetFormat | None = Field(
        None,
        description="Only for document_type=cell. Default xlsx.",
    )


class DocumentsRenameArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="file_id of the Documents binding.")
    title: str = Field(..., min_length=1, max_length=500, description="New document title.")


class DocumentsMoveArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="file_id to move.")
    catalog_id: str = Field(..., min_length=1, description="Destination catalog_id.")


class DocumentsCopyArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="Source file_id.")
    catalog_id: str = Field(..., min_length=1, description="Destination catalog_id.")
    title: str | None = Field(
        None,
        min_length=1,
        max_length=500,
        description="Optional title for the copy. Default: «{title} (copy)».",
    )


class DocumentsFileIdArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="file_id of the Documents binding.")


class DocumentsListCatalogArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    catalog_id: str | None = Field(
        None,
        description=(
            "Каталог для browse. Без параметра — корень: только каталоги с "
            "parent_catalog_id=null (документов на виртуальном корне нет)."
        ),
    )


class DocumentsFindArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(..., min_length=1, max_length=500, description="Поисковый запрос.")
    catalog_id: str | None = Field(
        None,
        description="Scope каталога. Для semantic обязателен; для lexical без него — весь namespace.",
    )
    mode: FindMode = Field(
        "auto",
        description=(
            "auto — semantic если rag_index_enabled, иначе lexical; "
            "semantic без индекса возвращает rag_index_disabled; lexical всегда title search."
        ),
    )
    limit: int = Field(20, ge=1, le=50, description="Лимит результатов.")


class DocumentsReadArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="ID файла платформы (Documents).")
    page_start: int = Field(0, ge=0, description="Первая страница (0-based), как у read_file.")
    page_end: int = Field(-1, description="Последняя страница включительно; -1 — до конца.")
    budget: int = Field(MAX_READ_BUDGET, ge=0, description="Лимит символов результата.")


class DocumentsGetLinkArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="ID документа Documents.")
    kind: LinkKind = Field(
        "editor",
        description="editor — SPA path /documents/edit/...; preview — preview_url из BFF.",
    )


class DocumentsCreateCatalogArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=500, description="Catalog folder title.")
    is_public: bool = Field(
        True,
        description="company_visible for the whole company in this namespace.",
    )
    parent_catalog_id: str | None = Field(
        None,
        description="Optional parent folder. Only parent owner may create a child.",
    )


class DocumentsUpdateCatalogArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    catalog_id: str = Field(..., min_length=1, description="catalog_id to update.")
    title: str | None = Field(None, min_length=1, max_length=500, description="New title.")
    is_public: bool | None = Field(None, description="Company-visible flag.")


class DocumentsCatalogIdArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    catalog_id: str = Field(..., min_length=1, description="catalog_id.")


class DocumentsAddCatalogMemberArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    catalog_id: str = Field(..., min_length=1, description="catalog_id.")
    user_id: str = Field(
        ...,
        min_length=1,
        description="Member user_id from team_resolve_user / team_list_members.",
    )


class DocumentsAccessArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    resource_kind: AccessResourceKind = Field(
        ...,
        description="catalog — folder ACL; document — file_id binding ACL.",
    )
    resource_id: str = Field(
        ...,
        min_length=1,
        description="catalog_id when resource_kind=catalog; file_id when document.",
    )


class DocumentsPatchAccessArgs(DocumentsAccessArgs):
    company_visible: bool | None = Field(None, description="Whole-company visibility.")
    link_enabled: bool | None = Field(None, description="Enable/disable public link.")
    link_permission: LinkPermission | None = Field(
        None,
        description="Public link permission when link is enabled.",
    )
    member_user_ids: list[str] | None = Field(
        None,
        description="Full replacement member list when provided.",
    )
