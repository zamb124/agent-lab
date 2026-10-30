"""
Явная привязка конфигурации парсинга/нарезки при upload (без id в БД).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.rag_indexing_schema import IndexProfileConfig


@dataclass(frozen=True)
class UploadProfileBinding:
    """Валидированный конфиг для парсинга/нарезки при индексации в pgvector."""

    config: IndexProfileConfig
