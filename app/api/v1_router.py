"""
API v1 роутер - объединяет все суброутеры из app/api/v1/
"""

from fastapi import APIRouter

# Импорт всех суброутеров v1
from app.api.v1 import (
    webhooks,
    admin,
    telegram,
    whatsapp,
    tokens,
    auth,
    flows,
    fashn,
    files,
    leads,
    payments,
    admin_payments,
    variables,
    knowledge_base
)

# Создание главного роутера v1
router = APIRouter(tags=["v1"])

# Публичное Platform API
router.include_router(flows.router, prefix="/flows")
router.include_router(files.router, prefix="/files")
router.include_router(payments.router)
router.include_router(fashn.router, prefix="/fashn")
router.include_router(knowledge_base.router)
router.include_router(leads.router)

# Внутренние API (скрытые от публичной документации)
router.include_router(webhooks.router, tags=["webhooks"], include_in_schema=False)
router.include_router(admin.router, prefix="/admin", tags=["admin"], include_in_schema=False)
router.include_router(telegram.router, tags=["telegram"], include_in_schema=False)
router.include_router(whatsapp.router, tags=["whatsapp"], include_in_schema=False)
router.include_router(tokens.router, tags=["tokens"], include_in_schema=False)
router.include_router(admin_payments.router, tags=["admin-payments"], include_in_schema=False)
router.include_router(variables.router, tags=["variables"], include_in_schema=False)
