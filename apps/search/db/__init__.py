"""Search DB package."""

from apps.search.db.base import SearchDatabase
from apps.search.db.models import Base

__all__ = ["Base", "SearchDatabase"]
