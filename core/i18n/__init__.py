"""
Интернационализация - переводы и локализация.

Включает:
- service.py - TranslationManager для управления переводами
"""

from core.i18n.service import TranslationManager, get_translation_manager, t

__all__ = [
    "TranslationManager",
    "get_translation_manager",
    "t",
]
