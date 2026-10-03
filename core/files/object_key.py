"""Стабильный ключ объекта: путь в дереве его не меняет."""

from __future__ import annotations


def object_key(company_id: str, file_id: str, version: str, original_name: str) -> str:
    if company_id.strip() == "" or file_id.strip() == "" or version.strip() == "":
        raise ValueError("company_id, file_id and version are required")
    safe_name = original_name.replace("/", "_").replace("\\", "_")
    if safe_name.strip() == "":
        safe_name = "object"
    return f"companies/{company_id}/{file_id}/{version}/{safe_name}"
