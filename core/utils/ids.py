"""Идентификаторы сущностей платформы: ``<prefix>_<24 hex>``."""

import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"
