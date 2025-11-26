"""
Админские endpoints для управления платежами.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.payments import PaymentSyncService
from apps.agents.dependencies import ContextDep

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/payments", tags=["admin-payments"])


class SyncResponse(BaseModel):
    """Результат синхронизации"""
    total_pending: int
    checked: int
    found: int
    updated: int


@router.post("/sync/{company_id}", response_model=SyncResponse)
async def sync_company_payments(company_id: str, context: ContextDep):
    """
    Ручная синхронизация pending транзакций компании.
    Проверяет через API провайдера не пропустили ли webhook.
    """
    
    # Проверка прав (только админ)
    user = context.user
    if "admin" not in user.groups:
        raise HTTPException(403, "Доступ запрещен. Требуются права администратора.")
    
    logger.info(f"Запрос на синхронизацию платежей компании {company_id} от {user.user_id}")
    
    sync_service = PaymentSyncService()
    
    try:
        stats = await sync_service.sync_pending_transactions(company_id)
        
        return SyncResponse(
            total_pending=stats["total_pending"],
            checked=stats["checked"],
            found=stats["found"],
            updated=stats["updated"]
        )
        
    except Exception as e:
        logger.error(f"Ошибка синхронизации: {e}", exc_info=True)
        raise HTTPException(500, f"Ошибка синхронизации: {str(e)}")


@router.post("/sync/all")
async def sync_all_payments(context: ContextDep):
    """
    Синхронизация всех pending транзакций всех компаний.
    Только для системных админов.
    """
    
    user = context.user
    if "admin" not in user.groups:
        raise HTTPException(403, "Доступ запрещен")
    
    logger.info(f"Запрос на глобальную синхронизацию от {user.user_id}")
    
    sync_service = PaymentSyncService()
    
    try:
        stats = await sync_service.sync_all_companies()
        
        return {
            "companies_checked": stats["companies_checked"],
            "total_pending": stats["total_pending"],
            "total_found": stats["total_found"],
            "total_updated": stats["total_updated"],
            "errors": stats["errors"]
        }
        
    except Exception as e:
        logger.error(f"Ошибка глобальной синхронизации: {e}", exc_info=True)
        raise HTTPException(500, f"Ошибка синхронизации: {str(e)}")
