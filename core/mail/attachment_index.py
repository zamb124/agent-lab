"""Idempotent file_id index for inbound mail attachments."""

from __future__ import annotations

import json

from core.db.storage import Storage


class MailAttachmentFileIndex:
    def __init__(self, storage: Storage) -> None:
        self._storage: Storage = storage

    def _key(self, mailbox_binding_id: str, mail_uid: str, attachment_index: int) -> str:
        return f"mail_attachment:{mailbox_binding_id}:{mail_uid}:{attachment_index}"

    async def get(
        self,
        *,
        mailbox_binding_id: str,
        mail_uid: str,
        attachment_index: int,
    ) -> str | None:
        raw = await self._storage.get(
            self._key(mailbox_binding_id, mail_uid, attachment_index),
            force_global=True,
        )
        if raw is None:
            return None
        # Storage.get returns JSON string scalars without wrapping quotes.
        file_id = raw.strip()
        if not file_id:
            raise ValueError("empty mail attachment file_id index value")
        return file_id

    async def set(
        self,
        *,
        mailbox_binding_id: str,
        mail_uid: str,
        attachment_index: int,
        file_id: str,
    ) -> None:
        if not file_id.strip():
            raise ValueError("file_id required for mail attachment index")
        # Storage.set parses value as JSON; bare UUID is not valid JSON text.
        _ = await self._storage.set(
            self._key(mailbox_binding_id, mail_uid, attachment_index),
            json.dumps(file_id),
            force_global=True,
        )
