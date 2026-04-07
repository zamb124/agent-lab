"""
Async HTTP-клиент Google Docs API v1 и Google Drive API v3.

Авторизация через Service Account (google-auth).
HTTP — httpx через SmartProxyClient платформы (прокси, retry).

Docs API: create, get, batchUpdate.
Drive API: upload DOCX с конвертацией, share.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from google.oauth2 import service_account as sa

from core.http import get_httpx_client
from core.logging import get_logger

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
        self.status_code = status_code
        super().__init__(f"Google API {status_code}: {message}")


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
                "или access_token (OAuth2 Bearer-токен)."
            )
        if subject and not credentials_json:
            raise ValueError(
                "subject (impersonation) работает только с credentials_json."
            )

        self._credentials: sa.Credentials | None = None
        self._static_token: str | None = None

        if credentials_json:
            info = json.loads(credentials_json)
            creds = sa.Credentials.from_service_account_info(
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

        if not self._credentials.valid:
            from google.auth.transport.requests import Request as AuthRequest

            self._credentials.refresh(AuthRequest())
        return {"Authorization": f"Bearer {self._credentials.token}"}

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        hdrs = {**self._auth_headers(), **(headers or {})}
        client = get_httpx_client(timeout=timeout)
        if method == "GET":
            resp = await client.get(url, headers=hdrs)
        elif method == "POST":
            if content is not None:
                resp = await client.post(url, headers=hdrs, content=content)
            else:
                resp = await client.post(url, headers=hdrs, json=json_body or {})
        elif method == "PATCH":
            resp = await client.patch(url, headers=hdrs, json=json_body or {})
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code >= 400:
            raise GoogleDocsClientError(resp.status_code, resp.text)
        if resp.status_code == 204:
            return {}
        return resp.json()

    # ── Docs API ─────────────────────────────────────────────────

    async def create_document(self, title: str) -> dict[str, Any]:
        """POST /v1/documents — пустой документ с заголовком."""
        return await self._request("POST", _DOCS_BASE, json_body={"title": title})

    async def get_document(self, document_id: str) -> dict[str, Any]:
        """GET /v1/documents/{documentId} — полная структура документа."""
        return await self._request("GET", f"{_DOCS_BASE}/{document_id}")

    async def read_as_text(self, document_id: str) -> str:
        """Читает документ и извлекает plain-text из JSON-структуры."""
        doc = await self.get_document(document_id)
        return _extract_text(doc)

    async def batch_update(
        self, document_id: str, requests: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """POST /v1/documents/{documentId}:batchUpdate — атомарное обновление."""
        return await self._request(
            "POST",
            f"{_DOCS_BASE}/{document_id}:batchUpdate",
            json_body={"requests": requests},
        )

    # ── высокоуровневые обёртки над batchUpdate ──────────────────

    async def append_text(self, document_id: str, text: str) -> dict[str, Any]:
        """Добавляет текст в конец документа (перед финальным \\n)."""
        doc = await self.get_document(document_id)
        end_index = _get_body_end_index(doc)
        return await self.batch_update(
            document_id,
            [{"insertText": {"location": {"index": end_index}, "text": text}}],
        )

    async def insert_text(
        self, document_id: str, text: str, index: int
    ) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
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

    async def upload_docx(self, title: str, docx_bytes: bytes) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        """Выдаёт доступ к документу по email (Drive permissions API)."""
        url = f"{_DRIVE_BASE}/files/{document_id}/permissions"
        return await self._request(
            "POST",
            url,
            json_body={"type": "user", "role": role, "emailAddress": email},
        )

    async def share_document_anyone(
        self,
        document_id: str,
        role: str = "reader",
    ) -> dict[str, Any]:
        """Делает документ доступным по ссылке (anyone with link)."""
        url = f"{_DRIVE_BASE}/files/{document_id}/permissions"
        return await self._request(
            "POST",
            url,
            json_body={"type": "anyone", "role": role},
        )


# ── утилиты ──────────────────────────────────────────────────────


def _extract_text(doc: dict[str, Any]) -> str:
    """
    Извлекает plain-text из JSON-структуры Google Docs.

    Обход: body.content[].paragraph.elements[].textRun.content.
    """
    parts: list[str] = []
    body = doc.get("body", {})
    for structural in body.get("content", []):
        paragraph = structural.get("paragraph")
        if paragraph is None:
            continue
        for element in paragraph.get("elements", []):
            text_run = element.get("textRun")
            if text_run is not None:
                parts.append(text_run.get("content", ""))
    return "".join(parts)


def _get_body_end_index(doc: dict[str, Any]) -> int:
    """
    Возвращает индекс для вставки текста в конец документа.

    Последний элемент body.content содержит endIndex; вставка
    на endIndex-1 (перед финальным \\n).
    """
    body = doc.get("body", {})
    content = body.get("content", [])
    if not content:
        return 1
    last = content[-1]
    end = last.get("endIndex", 1)
    return max(end - 1, 1)
