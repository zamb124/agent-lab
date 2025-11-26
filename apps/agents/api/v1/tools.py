"""
API для работы с инструментами
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/tools",
    tags=["tools"]
)

