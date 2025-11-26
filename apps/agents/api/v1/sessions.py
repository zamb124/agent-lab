"""
API для работы с сессиями
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["sessions"]
)




