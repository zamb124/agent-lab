"""
Артефакты daily / period summary в S3 (долговечное хранилище рядом с Redis hot-cache).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from botocore.exceptions import ClientError

from apps.crm.types import JsonObject
from core.files.s3_client import S3ClientFactory
from core.logging import get_logger

logger = get_logger(__name__)

_SCHEMA_VERSION = 1


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
        except ClientError as exc:
            response = cast(dict[str, object], exc.response)
            error = response.get("Error")
            error_data = cast(dict[str, object], error) if isinstance(error, dict) else {}
            code = str(error_data.get("Code", ""))
            if code in ("404", "NoSuchKey", "NotFound", "NoSuchBucket"):
                return None
            raise
        finally:
            await client.close()
        data = cast(object, json.loads(raw.decode("utf-8")))
        if not isinstance(data, dict):
            raise ValueError("Daily summary S3 payload must be a JSON object")
        return cast(JsonObject, data)

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
        except ClientError as exc:
            response = cast(dict[str, object], exc.response)
            error = response.get("Error")
            error_data = cast(dict[str, object], error) if isinstance(error, dict) else {}
            code = str(error_data.get("Code", ""))
            if code in ("404", "NoSuchKey", "NotFound", "NoSuchBucket"):
                return None
            raise
        finally:
            await client.close()
        data = cast(object, json.loads(raw.decode("utf-8")))
        if not isinstance(data, dict):
            raise ValueError("Period summary S3 payload must be a JSON object")
        return cast(JsonObject, data)
