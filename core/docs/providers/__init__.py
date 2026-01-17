"""
Провайдеры документации для разных языков.
"""

from core.docs.providers.base import BaseDocProvider
from core.docs.providers.python import PythonDocProvider

__all__ = ["BaseDocProvider", "PythonDocProvider"]
