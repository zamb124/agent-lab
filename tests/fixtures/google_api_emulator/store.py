"""In-memory Google Workspace resources for the local API emulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from core.types import JsonObject, JsonValue


@dataclass
class SheetTab:
    sheet_id: int
    title: str
    index: int
    # sparse grid: row -> col -> cell string
    cells: dict[int, dict[int, str]] = field(default_factory=dict)


@dataclass
class SpreadsheetRecord:
    spreadsheet_id: str
    title: str
    sheets: list[SheetTab]
    next_sheet_id: int = 1


@dataclass
class DocumentRecord:
    document_id: str
    title: str
    # plain text body; endIndex semantics like Docs (leading section + trailing newline)
    text: str = "\n"


@dataclass
class EmulatorStore:
    tokens: set[str] = field(default_factory=set)
    spreadsheets: dict[str, SpreadsheetRecord] = field(default_factory=dict)
    documents: dict[str, DocumentRecord] = field(default_factory=dict)
    permissions: dict[str, list[JsonObject]] = field(default_factory=dict)
    next_sheet_id_global: int = 1000

    def allow_token(self, token: str) -> None:
        if not token.strip():
            raise ValueError("token must be non-empty")
        self.tokens.add(token.strip())

    def is_authorized(self, authorization: str | None) -> bool:
        if authorization is None or not authorization.startswith("Bearer "):
            return False
        token = authorization.removeprefix("Bearer ").strip()
        return token in self.tokens

    def create_spreadsheet(
        self,
        title: str,
        sheet_titles: list[str] | None,
    ) -> SpreadsheetRecord:
        spreadsheet_id = f"ss_{uuid4().hex[:16]}"
        titles = sheet_titles if sheet_titles else ["Sheet1"]
        sheets: list[SheetTab] = []
        for index, sheet_title in enumerate(titles):
            sheet_id = self.next_sheet_id_global
            self.next_sheet_id_global += 1
            sheets.append(SheetTab(sheet_id=sheet_id, title=sheet_title, index=index))
        record = SpreadsheetRecord(
            spreadsheet_id=spreadsheet_id,
            title=title,
            sheets=sheets,
            next_sheet_id=self.next_sheet_id_global,
        )
        self.spreadsheets[spreadsheet_id] = record
        self.permissions[spreadsheet_id] = []
        return record

    def create_document(self, title: str) -> DocumentRecord:
        document_id = f"doc_{uuid4().hex[:16]}"
        record = DocumentRecord(document_id=document_id, title=title, text="\n")
        self.documents[document_id] = record
        self.permissions[document_id] = []
        return record

    def get_spreadsheet(self, spreadsheet_id: str) -> SpreadsheetRecord | None:
        return self.spreadsheets.get(spreadsheet_id)

    def get_document(self, document_id: str) -> DocumentRecord | None:
        return self.documents.get(document_id)


def spreadsheet_to_json(record: SpreadsheetRecord) -> JsonObject:
    return {
        "spreadsheetId": record.spreadsheet_id,
        "properties": {"title": record.title},
        "sheets": [
            {
                "properties": {
                    "sheetId": sheet.sheet_id,
                    "title": sheet.title,
                    "index": sheet.index,
                }
            }
            for sheet in sorted(record.sheets, key=lambda item: item.index)
        ],
    }


def document_to_json(record: DocumentRecord) -> JsonObject:
    # Minimal Docs structure for read_as_text / append endIndex helpers.
    body_text = record.text if record.text.endswith("\n") else record.text + "\n"
    end_index = max(len(body_text), 2)
    elements: list[JsonValue] = []
    if body_text not in ("", "\n"):
        content_without_final = body_text[:-1] if body_text.endswith("\n") else body_text
        if content_without_final:
            elements.append(
                {
                    "startIndex": 1,
                    "endIndex": 1 + len(content_without_final),
                    "textRun": {"content": content_without_final},
                }
            )
    elements.append(
        {
            "startIndex": end_index - 1,
            "endIndex": end_index,
            "textRun": {"content": "\n"},
        }
    )
    return {
        "documentId": record.document_id,
        "title": record.title,
        "body": {
            "content": [
                {
                    "startIndex": 1,
                    "endIndex": end_index,
                    "paragraph": {"elements": elements},
                }
            ]
        },
    }


def google_error(status_code: int, status: str, message: str) -> dict[str, Any]:
    return {
        "error": {
            "code": status_code,
            "message": message,
            "status": status,
        }
    }
