"""
API endpoints для платежей и пополнения баланса.
"""

import logging
from fastapi import APIRouter, HTTPException, Request

from app.frontend.dependencies import ContextDep
from app.core.clients.payment_providers.factory import PaymentProviderFactory
from app.services.payment_service import PaymentService
from app.models.payment_models import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    TransactionResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/payments",
    tags=["Платежи и баланс"],
    responses={
        404: {"description": "Транзакция не найдена"},
        500: {"description": "Ошибка платежной системы"}
    }
)


@router.post("/create", response_model=CreatePaymentResponse, summary="Создать платеж")
async def create_payment(request: CreatePaymentRequest, context: ContextDep):
    """
    Создает транзакцию пополнения баланса и генерирует платежную ссылку.
    
    **Процесс оплаты:**
    1. Отправляете запрос с суммой → получаете payment_url
    2. Перенаправляете пользователя на payment_url
    3. Пользователь оплачивает через платежную систему
    4. Платежная система отправляет webhook с подтверждением
    5. Баланс компании пополняется автоматически
    
    **Поддерживаемые провайдеры:**
    - YooMoney (Юмани)
    - ЮKassa
    
    **Минимальная сумма:** 100₽  
    **Максимальная сумма:** 1,000,000₽
    
    Args:
        request: Сумма пополнения и опциональный провайдер
        
    Returns:
        transaction_id и payment_url для перенаправления пользователя
    """
    
    user = context.user
    company = context.active_company
    
    logger.info(
        f"Запрос на создание платежа: компания={company.company_id}, "
        f"пользователь={user.user_id}, сумма={request.amount}₽"
    )
    
    payment_service = PaymentService()
    
    provider_name = request.provider or company.payment_provider
    if not provider_name:
        available = PaymentProviderFactory.get_available_providers()
        if not available:
            logger.error("Нет доступных платежных провайдеров")
            raise HTTPException(400, "Нет доступных платежных провайдеров")
        provider_name = next(iter(available.keys()))
    
    provider = PaymentProviderFactory.get_provider(provider_name)
    if not provider:
        logger.error(f"Провайдер {provider_name} недоступен")
        raise HTTPException(400, f"Провайдер {provider_name} недоступен")
    
    try:
        result = await payment_service.create_payment(
            company=company,
            user=user,
            amount=request.amount,
            provider=provider
        )
        
        return CreatePaymentResponse(
            transaction_id=result["transaction_id"],
            payment_url=result["payment_url"],
            provider=provider_name,
            status="pending",
            amount=request.amount
        )
        
    except Exception as e:
        logger.error(f"Ошибка создания платежа: {e}", exc_info=True)
        raise HTTPException(500, f"Ошибка создания платежа: {str(e)}")


@router.post("/webhook/{provider_name}")
async def payment_webhook(provider_name: str, request: Request):
    """
    Универсальный webhook для приема уведомлений от платежных провайдеров.
    
    URL для настройки в провайдерах:
    - YooMoney: https://your-domain.com/api/v1/payments/webhook/yoomoney_main
    - ЮKassa: https://your-domain.com/api/v1/payments/webhook/yukassa_main
    
    Провайдер должен совпадать с именем в конфигурации.
    """
    
    logger.info(f"📨 Получен POST webhook от провайдера: {provider_name}")
    
    # Логируем headers
    logger.info(f"📋 Headers: {dict(request.headers)}")
    
    # Логируем метод и content-type
    logger.info(f"🔧 Method: {request.method}, Content-Type: {request.headers.get('content-type')}")
    
    provider = PaymentProviderFactory.get_provider(provider_name)
    if not provider:
        logger.error(f"Провайдер {provider_name} не найден")
        raise HTTPException(404, f"Провайдер {provider_name} не найден")
    
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        webhook_data = dict(await request.form())
        logger.info(f"📦 Данные webhook (form-urlencoded): {webhook_data}")
    else:
        webhook_data = await request.json()
        logger.info(f"📦 Данные webhook (json): {webhook_data}")
    
    try:
        verification_result = await provider.verify_webhook(webhook_data)
        
        if not verification_result.is_valid:
            logger.error(
                f"Неверная подпись webhook от {provider_name}: "
                f"{verification_result.error_message}"
            )
            raise HTTPException(401, "Invalid signature")
        
        payment_service = PaymentService()
        await payment_service.process_webhook(
            verification_result=verification_result,
            provider_name=provider_name,
            raw_data=webhook_data
        )
        
        logger.info(f"✅ Webhook от {provider_name} успешно обработан")
        
        return {"status": "success"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}", exc_info=True)
        raise HTTPException(500, f"Ошибка обработки webhook: {str(e)}")


@router.get("/transaction/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(transaction_id: str, context: ContextDep):
    """
    Получить информацию о транзакции.
    Доступно только для компании, которая создала транзакцию.
    """
    
    company = context.active_company
    
    payment_service = PaymentService()
    transaction = await payment_service.get_transaction(transaction_id)
    
    if not transaction:
        raise HTTPException(404, "Транзакция не найдена")
    
    if transaction.company_id != company.company_id:
        raise HTTPException(403, "Доступ запрещен")
    
    return TransactionResponse(
        transaction_id=transaction.transaction_id,
        company_id=transaction.company_id,
        amount=transaction.amount,
        status=transaction.status,
        payment_provider=transaction.payment_provider,
        external_payment_id=transaction.external_payment_id,
        created_at=transaction.created_at,
        completed_at=transaction.completed_at
    )


@router.get("/history")
async def get_payment_history(limit: int = 50, offset: int = 0, context: ContextDep = None):
    """
    История платежей компании.
    Возвращает список транзакций отсортированных по дате (новые первые).
    """
    
    company = context.active_company
    
    payment_service = PaymentService()
    transactions = await payment_service.get_company_transactions(
        company_id=company.company_id,
        limit=limit,
        offset=offset
    )
    
    return {
        "transactions": [
            {
                "transaction_id": t.transaction_id,
                "amount": t.amount,
                "status": t.status,
                "payment_provider": t.payment_provider,
                "created_at": t.created_at.isoformat(),
                "completed_at": t.completed_at.isoformat() if t.completed_at else None
            }
            for t in transactions
        ],
        "total": len(transactions),
        "limit": limit,
        "offset": offset
    }


@router.get("/providers")
async def get_available_providers():
    """
    Список доступных платежных провайдеров.
    Публичный endpoint, не требует авторизации.
    """
    
    providers = PaymentProviderFactory.list_providers()
    
    return {
        "providers": providers,
        "total": len(providers)
    }
