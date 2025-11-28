"""
API для работы с инструментами
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/tools",
    tags=["tools"]
)

