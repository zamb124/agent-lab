"""
Async HTTP-клиент Google Docs API v1 и Google Drive API v3.

Авторизация через Service Account (google-auth).
HTTP — httpx через SmartProxyClient платформы (прокси, retry).

Docs API: create, get, batchUpdate.
Drive API: upload DOCX с конвертацией, share.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol, cast

from google.auth.transport.requests import Request as AuthRequest
from google.oauth2 import service_account as sa

from core.http import get_httpx_client
from core.logging import get_logger
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_object,
    require_json_array,
    require_json_object,
)

logger = get_logger(__name__)

_DOCS_BASE = "https://docs.googleapis.com/v1/documents"
_DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3/files"
_DRIVE_BASE = "https://www.googleapis.com/drive/v3"

_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_GDOC_MIME = "application/vnd.google-apps.document"


class GoogleDocsClientError(Exception):
    """Ошибка Google Docs / Drive API."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code: int = status_code
        super().__init__(f"Google API {status_code}: {message}")


class _GoogleCredentials(Protocol):
    valid: bool
    token: str | None

    def refresh(self, request: AuthRequest) -> None: ...

    def with_subject(self, subject: str) -> _GoogleCredentials: ...


class _FromServiceAccountInfo(Protocol):
    def __call__(
        self,
        info: JsonObject,
        *,
        scopes: list[str],
    ) -> _GoogleCredentials: ...


class GoogleDocsClient:
    """
    Async-клиент для Google Docs API v1 + Google Drive API v3.

    Два режима авторизации (передавать ровно один):
      credentials_json — JSON-строка ключа Service Account;
                         библиотека google-auth автоматически выпускает
                         и обновляет access token (живёт 1 час).
      access_token     — готовый OAuth2 Bearer-токен.
                         Google не выпускает бессрочных токенов: стандартный
                         access token живёт 1 час, поэтому использовать
                         этот режим имеет смысл для разовых операций
                         или если приложение само обновляет токен.

    subject — email пользователя Google Workspace для domain-wide delegation.
              SA выпускает токен от имени этого пользователя (документы
              попадают в его Drive). Работает только с credentials_json.
    """

    def __init__(
        self,
        *,
        credentials_json: str | None = None,
        access_token: str | None = None,
        subject: str | None = None,
    ) -> None:
        if credentials_json and access_token:
            raise ValueError(
                "Передайте credentials_json или access_token, не оба."
            )
        if not credentials_json and not access_token:
            raise ValueError(
                "Передайте credentials_json (Service Account JSON) "
                + "или access_token (OAuth2 Bearer-токен)."
            )
        if subject and not credentials_json:
            raise ValueError(
                "subject (impersonation) работает только с credentials_json."
            )

        self._credentials: _GoogleCredentials | None = None
        self._static_token: str | None = None

        if credentials_json:
            info = parse_json_object(credentials_json, "google.service_account")
            from_service_account_info = cast(
                _FromServiceAccountInfo,
                sa.Credentials.from_service_account_info,
            )
            creds = from_service_account_info(
                info, scopes=_SCOPES
            )
            if subject:
                creds = creds.with_subject(subject)
            self._credentials = creds
        else:
            self._static_token = access_token

    # ── helpers ──────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        if self._static_token:
            return {"Authorization": f"Bearer {self._static_token}"}

        credentials = self._credentials
        if credentials is None:
            raise RuntimeError("GoogleDocsClient credentials are not configured")
        if not credentials.valid:
            credentials.refresh(AuthRequest())
        token = credentials.token
        if token is None or token == "":
            raise RuntimeError("GoogleDocsClient credentials did not produce access token")
        return {"Authorization": f"Bearer {token}"}

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: JsonObject | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> JsonObject:
        hdrs = {**self._auth_headers(), **(headers or {})}
        client = get_httpx_client(timeout=timeout)
        if method == "GET":
            resp = await client.get(url, headers=hdrs)
        elif method == "POST":
            if content is not None:
                resp = await client.post(url, headers=hdrs, content=content)
            else:
                if json_body is None:
                    raise ValueError("GoogleDocsClient POST requires json_body or content")
                resp = await client.post(url, headers=hdrs, json=json_body)
        elif method == "PATCH":
            if json_body is None:
                raise ValueError("GoogleDocsClient PATCH requires json_body")
            resp = await client.patch(url, headers=hdrs, json=json_body)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code >= 400:
            raise GoogleDocsClientError(resp.status_code, resp.text)
        if resp.status_code == 204:
            return {}
        return parse_json_object(resp.content, f"Google API {method} {url}")

    # ── Docs API ─────────────────────────────────────────────────

    async def create_document(self, title: str) -> JsonObject:
        """POST /v1/documents — пустой документ с заголовком."""
        return await self._request(
            "POST",
            _DOCS_BASE,
            json_body=require_json_object({"title": title}, "gdocs.create_document"),
        )

    async def get_document(self, document_id: str) -> JsonObject:
        """GET /v1/documents/{documentId} — полная структура документа."""
        return await self._request("GET", f"{_DOCS_BASE}/{document_id}")

    async def read_as_text(self, document_id: str) -> str:
        """Читает документ и извлекает plain-text из JSON-структуры."""
        doc = await self.get_document(document_id)
        return _extract_text(doc)

    async def batch_update(
        self, document_id: str, requests: list[JsonObject]
    ) -> JsonObject:
        """POST /v1/documents/{documentId}:batchUpdate — атомарное обновление."""
        return await self._request(
            "POST",
            f"{_DOCS_BASE}/{document_id}:batchUpdate",
            json_body=require_json_object({"requests": requests}, "gdocs.batch_update"),
        )

    # ── высокоуровневые обёртки над batchUpdate ──────────────────

    async def append_text(self, document_id: str, text: str) -> JsonObject:
        """Добавляет текст в конец документа (перед финальным \\n)."""
        doc = await self.get_document(document_id)
        end_index = _get_body_end_index(doc)
        return await self.batch_update(
            document_id,
            [{"insertText": {"location": {"index": end_index}, "text": text}}],
        )

    async def insert_text(
        self, document_id: str, text: str, index: int
    ) -> JsonObject:
        """Вставляет текст в указанную позицию (1-based index)."""
        return await self.batch_update(
            document_id,
            [{"insertText": {"location": {"index": index}, "text": text}}],
        )

    async def find_and_replace(
        self,
        document_id: str,
        find: str,
        replace: str,
        *,
        match_case: bool = True,
    ) -> JsonObject:
        return await self.batch_update(
            document_id,
            [
                {
                    "replaceAllText": {
                        "containsText": {"text": find, "matchCase": match_case},
                        "replaceText": replace,
                    }
                }
            ],
        )

    async def delete_range(
        self, document_id: str, start_index: int, end_index: int
    ) -> JsonObject:
        return await self.batch_update(
            document_id,
            [
                {
                    "deleteContentRange": {
                        "range": {
                            "startIndex": start_index,
                            "endIndex": end_index,
                            "segmentId": "",
                        }
                    }
                }
            ],
        )

    # ── Drive API ────────────────────────────────────────────────

    async def upload_docx(self, title: str, docx_bytes: bytes) -> JsonObject:
        """
        Multipart upload DOCX в Google Drive с конвертацией в Google Docs.

        Возвращает dict c id, name, mimeType, webViewLink.
        """
        boundary = "----platform_gdocs_boundary"
        metadata = json.dumps({"name": title, "mimeType": _GDOC_MIME})

        body = (
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{metadata}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {_DOCX_MIME}\r\n\r\n"
        ).encode("utf-8") + docx_bytes + f"\r\n--{boundary}--".encode("utf-8")

        url = f"{_DRIVE_UPLOAD_BASE}?uploadType=multipart&fields=id,name,mimeType,webViewLink"
        return await self._request(
            "POST",
            url,
            content=body,
            headers={
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
        )

    async def share_document(
        self,
        document_id: str,
        email: str,
        role: str = "reader",
    ) -> JsonObject:
        """Выдаёт доступ к документу по email (Drive permissions API)."""
        url = f"{_DRIVE_BASE}/files/{document_id}/permissions"
        return await self._request(
            "POST",
            url,
            json_body=require_json_object(
                {"type": "user", "role": role, "emailAddress": email},
                "gdocs.share_document",
            ),
        )

    async def share_document_anyone(
        self,
        document_id: str,
        role: str = "reader",
    ) -> JsonObject:
        """Делает документ доступным по ссылке (anyone with link)."""
        url = f"{_DRIVE_BASE}/files/{document_id}/permissions"
        return await self._request(
            "POST",
            url,
            json_body=require_json_object(
                {"type": "anyone", "role": role},
                "gdocs.share_document_anyone",
            ),
        )


# ── утилиты ──────────────────────────────────────────────────────


def _extract_text(doc: JsonObject) -> str:
    """
    Извлекает plain-text из JSON-структуры Google Docs.

    Обход: body.content[].paragraph.elements[].textRun.content.
    """
    parts: list[str] = []
    body = _json_object_or_none(doc.get("body"))
    if body is None:
        return ""
    content = _json_array_or_empty(body.get("content"))
    for structural_raw in content:
        structural = _json_object_or_none(structural_raw)
        if structural is None:
            continue
        paragraph = _json_object_or_none(structural.get("paragraph"))
        if paragraph is None:
            continue
        elements = _json_array_or_empty(paragraph.get("elements"))
        for element_raw in elements:
            element = _json_object_or_none(element_raw)
            if element is None:
                continue
            text_run = _json_object_or_none(element.get("textRun"))
            if text_run is None:
                continue
            content_value = text_run.get("content")
            if isinstance(content_value, str):
                parts.append(content_value)
    return "".join(parts)


def _get_body_end_index(doc: JsonObject) -> int:
    """
    Возвращает индекс для вставки текста в конец документа.

    Последний элемент body.content содержит endIndex; вставка
    на endIndex-1 (перед финальным \\n).
    """
    body = _json_object_or_none(doc.get("body"))
    if body is None:
        return 1
    content = _json_array_or_empty(body.get("content"))
    if not content:
        return 1
    last = _json_object_or_none(content[-1])
    if last is None:
        return 1
    end = last.get("endIndex")
    if isinstance(end, bool) or not isinstance(end, int | float):
        return 1
    return max(int(end) - 1, 1)


def _json_object_or_none(value: JsonValue | None) -> JsonObject | None:
    if not isinstance(value, Mapping):
        return None
    return require_json_object(value, "gdocs.object")


def _json_array_or_empty(value: JsonValue | None) -> list[JsonValue]:
    if not isinstance(value, list):
        return []
    return require_json_array(value, "gdocs.array")
