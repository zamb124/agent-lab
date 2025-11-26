"""
API для работы с агентами
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"]
)

