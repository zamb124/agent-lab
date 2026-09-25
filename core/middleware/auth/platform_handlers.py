"""
Обработчики для платформ (Telegram webhook).
"""

from abc import ABC, abstractmethod
from typing import assert_never, override

from fastapi import HTTPException, Request
from pydantic import Field, ValidationError

from core.logging import get_logger
from core.models.base import FlexibleBaseModel
from core.models.identity_models import Company, User, UserStatus
from core.types import JsonObject

from .route_config import WebhookPlatform

logger = get_logger(__name__)


class TelegramWebhookUser(FlexibleBaseModel):
    id: int
    username: str | None = None
    first_name: str = Field(min_length=1)
    last_name: str | None = None


class TelegramWebhookMessage(FlexibleBaseModel):
    from_user: TelegramWebhookUser = Field(alias="from")


class TelegramWebhookPayload(FlexibleBaseModel):
    message: TelegramWebhookMessage


class PlatformHandler(ABC):
    """Базовый обработчик платформы"""

    async def extract_company_from_webhook_path(self, path: str, platform: str) -> Company:
        """Извлекает компанию из пути webhook"""
        prefix = f"/flows/api/v1/webhook/{platform}/"
        if not path.startswith(prefix):
            raise HTTPException(status_code=400, detail=f"Invalid webhook path: {path}")

        flow_key = path[len(prefix) :]
        parts = flow_key.split(":")

        if len(parts) < 4 or parts[0] != "company" or parts[2] != "flow":
            raise HTTPException(status_code=400, detail=f"Invalid flow key format: {flow_key}")

        company_id = parts[1]
        company = await Company.get(company_id)

        if not company:
            raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

        return company

    @abstractmethod
    async def create_user_from_request(
        self, request: Request, company: Company
    ) -> tuple[User, JsonObject]:
        raise NotImplementedError


class TelegramHandler(PlatformHandler):
    """Обработчик Telegram webhook"""

    @override
    async def create_user_from_request(
        self, request: Request, company: Company
    ) -> tuple[User, JsonObject]:
        """Создает пользователя из Telegram webhook данных"""
        body = await request.body()
        try:
            payload = TelegramWebhookPayload.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail="Invalid Telegram webhook payload") from exc

        tg_user = payload.message.from_user
        telegram_user_id = str(tg_user.id)
        username = tg_user.username or ""
        last_name = tg_user.last_name or ""

        full_name = f"{tg_user.first_name} {last_name}".strip()

        user = User(
            user_id=f"telegram_{telegram_user_id}",
            name=full_name,
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={company.company_id: ["user"]},
            active_company_id=company.company_id,
            messengers={"telegram": username} if username else {},
        )

        metadata: JsonObject = {
            "telegram_user_id": telegram_user_id,
            "username": username,
            "first_name": tg_user.first_name,
            "last_name": last_name,
        }

        return user, metadata


def get_platform_handler(platform: WebhookPlatform) -> PlatformHandler:
    """Возвращает обработчик для платформы"""
    if platform == "telegram":
        return TelegramHandler()
    assert_never(platform)
