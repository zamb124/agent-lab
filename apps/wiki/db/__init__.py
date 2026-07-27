"""Слой хранения wiki: подключение к БД и репозиторий."""

from apps.wiki.db.base import WikiDatabase
from apps.wiki.db.repositories.wiki_repository import WikiRepository

__all__ = ["WikiDatabase", "WikiRepository"]
