"""
API для работы с агентами
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/agents",
    tags=["agents"]
)

