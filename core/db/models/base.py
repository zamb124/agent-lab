"""
Базовый DeclarativeBase для всех SQLAlchemy-моделей платформы (SQLAlchemy 2.0).
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
