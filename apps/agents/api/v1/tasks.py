"""
API для работы с задачами
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"]
)




