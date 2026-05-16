"""
Артефакты daily / period summary в S3 (долговечное хранилище рядом с Redis hot-cache).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast as type_cast

from apps.crm.types import JsonObject
from core.files.s3_client import S3ClientFactory
from core.logging import get_logger

logger = get_logger(__name__)

_SCHEMA_VERSION = 1


def _s3_error_code(exc: Exception) -> str:
    response = type_cast(object, getattr(exc, "response", None))
    if not isinstance(response, dict):
        return ""
    response_data = type_cast(dict[str, object], response)
    error = response_data.get("Error")
    if not isinstance(error, dict):
        return ""
    error_data = type_cast(dict[str, object], error)
    code = error_data.get("Code")
    return code if isinstance(code, str) else ""


class DailySummaryArtifactService:
    """Чтение/запись JSON-снимков сводок в дефолтный bucket S3."""

    @staticmethod
    def _normalize_namespace(namespace: str | None) -> str:
        if namespace is None:
            return "all"
        if namespace.strip() == "":
            return "all"
        return namespace

    @classmethod
    def daily_object_key(cls, company_id: str, namespace: str | None, date_str: str) -> str:
        ns = cls._normalize_namespace(namespace)
        return f"crm/daily_summary/v{_SCHEMA_VERSION}/{company_id}/{ns}/{date_str}.json"

    @classmethod
    def period_object_key(
        cls,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
    ) -> str:
        ns = cls._normalize_namespace(namespace)
        return f"crm/period_summary/v{_SCHEMA_VERSION}/{company_id}/{ns}/{date_from}_{date_to}.json"

    async def put_daily_payload(
        self,
        *,
        company_id: str,
        namespace: str | None,
        date_str: str,
        payload: Mapping[str, object],
    ) -> None:
        key = self.daily_object_key(company_id, namespace, date_str)
        body = json.dumps(dict(payload), ensure_ascii=False, default=str).encode("utf-8")
        client = S3ClientFactory.create_default_client()
        try:
            _ = await client.upload_bytes(
                data=body,
                key=key,
                content_type="application/json; charset=utf-8",
            )
        finally:
            await client.close()

    async def get_daily_payload(
        self,
        *,
        company_id: str,
        namespace: str | None,
        date_str: str,
    ) -> JsonObject | None:
        key = self.daily_object_key(company_id, namespace, date_str)
        client = S3ClientFactory.create_default_client()
        try:
            raw = await client.download_bytes(key=key)
        except Exception as exc:
            code = _s3_error_code(exc)
            if code in ("404", "NoSuchKey", "NotFound", "NoSuchBucket"):
                return None
            raise
        finally:
            await client.close()
        data = type_cast(object, json.loads(raw.decode("utf-8")))
        if not isinstance(data, dict):
            raise ValueError("Daily summary S3 payload must be a JSON object")
        return type_cast(JsonObject, data)

    async def put_period_payload(
        self,
        *,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
        payload: Mapping[str, object],
    ) -> None:
        key = self.period_object_key(company_id, namespace, date_from, date_to)
        body = json.dumps(dict(payload), ensure_ascii=False, default=str).encode("utf-8")
        client = S3ClientFactory.create_default_client()
        try:
            _ = await client.upload_bytes(
                data=body,
                key=key,
                content_type="application/json; charset=utf-8",
            )
        finally:
            await client.close()

    async def get_period_payload(
        self,
        *,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
    ) -> JsonObject | None:
        key = self.period_object_key(company_id, namespace, date_from, date_to)
        client = S3ClientFactory.create_default_client()
        try:
            raw = await client.download_bytes(key=key)
        except Exception as exc:
            code = _s3_error_code(exc)
            if code in ("404", "NoSuchKey", "NotFound", "NoSuchBucket"):
                return None
            raise
        finally:
            await client.close()
        data = type_cast(object, json.loads(raw.decode("utf-8")))
        if not isinstance(data, dict):
            raise ValueError("Period summary S3 payload must be a JSON object")
        return type_cast(JsonObject, data)
