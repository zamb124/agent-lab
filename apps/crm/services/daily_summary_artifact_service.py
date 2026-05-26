"""
Артефакты daily / period summary в S3 (долговечное хранилище рядом с Redis hot-cache).
"""

from __future__ import annotations

import json

from botocore.exceptions import ClientError

from core.files.s3_client import S3ClientFactory
from core.logging import get_logger
from core.types import JsonObject, parse_json_object, require_json_object

logger = get_logger(__name__)

_SCHEMA_VERSION = 1
_S3_MISSING_ERROR_CODES = frozenset({"404", "NoSuchKey", "NotFound", "NoSuchBucket"})


def _s3_error_code(exc: ClientError) -> str:
    response = require_json_object(exc.response, "s3.error.response")
    error = require_json_object(response["Error"], "s3.error.response.Error")
    code = error["Code"]
    if not isinstance(code, str):
        raise ValueError("s3.error.response.Error.Code must be string")
    return code


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
        payload: JsonObject,
    ) -> None:
        key = self.daily_object_key(company_id, namespace, date_str)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
            if _s3_error_code(exc) in _S3_MISSING_ERROR_CODES:
                return None
            raise
        finally:
            await client.close()
        return parse_json_object(raw, "daily_summary.s3_payload")

    async def put_period_payload(
        self,
        *,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
        payload: JsonObject,
    ) -> None:
        key = self.period_object_key(company_id, namespace, date_from, date_to)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
            if _s3_error_code(exc) in _S3_MISSING_ERROR_CODES:
                return None
            raise
        finally:
            await client.close()
        return parse_json_object(raw, "period_summary.s3_payload")
