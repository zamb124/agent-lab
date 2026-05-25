"""
Провайдер для приема платежей через YooMoney (ЮMoney).
Quickpay для приема, OAuth API для сверки транзакций.

Документация:
- Quickpay: https://yoomoney.ru/docs/payment-buttons/using-api/forms
- HTTP-уведомления: https://yoomoney.ru/docs/wallet/using-api/notification-p2p-incoming
- OAuth: https://yoomoney.ru/docs/wallet/using-api/authorization/request-access-token
- operation-history: https://yoomoney.ru/docs/wallet/user-account/operation-history
- operation-details: https://yoomoney.ru/docs/wallet/user-account/operation-details
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Literal, override
from urllib.parse import urlencode

from pydantic import Field, ValidationError

from core.clients.payment.base_provider import (
    BasePaymentProvider,
    PaymentProviderConfig,
    PaymentRequest,
    PaymentResponse,
    WebhookVerificationResult,
)
from core.db.storage import Storage
from core.http import get_httpx_client
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.payment_models import PaymentStatus, PaymentSyncCandidate, PaymentSyncOperation
from core.types import JsonObject, parse_json_object, require_json_object

logger = get_logger(__name__)
YOOMONEY_TOKEN_LIFETIME_YEARS = 3
YOOMONEY_TOKEN_STORAGE_KEY = "yoomoney:access_token"
YOOMONEY_OAUTH_AUTHORIZE_URL = "https://yoomoney.ru/oauth/authorize"
YOOMONEY_OAUTH_TOKEN_URL = "https://yoomoney.ru/oauth/token"
YOOMONEY_QUICKPAY_URL = "https://yoomoney.ru/quickpay/confirm.xml"
YOOMONEY_API_URL = "https://yoomoney.ru/api"
YOOMONEY_MISSING_TOKEN_MESSAGE = (
    "YooMoney access_token не найден или истёк. "
    + "Выполните OAuth-авторизацию через /api/billing/yoomoney/authorize"
)

class YooMoneyConfig(PaymentProviderConfig[Literal["yoomoney"]]):
    """Конфигурация YooMoney провайдера"""
    provider_type: Literal["yoomoney"] = "yoomoney"
    account_number: str = Field(description="Номер кошелька YooMoney")
    notification_secret: str = Field(description="Секрет для проверки HTTP-уведомлений")
    quickpay_url: str = Field(
        default=YOOMONEY_QUICKPAY_URL,
        description="URL формы оплаты Quickpay"
    )
    client_id: str | None = Field(default=None, description="OAuth client_id приложения")
    client_secret: str | None = Field(default=None, description="OAuth client_secret приложения")
    access_token: str | None = Field(default=None, description="OAuth access_token (из env, загружается в storage при старте)")
    api_url: str = Field(
        default=YOOMONEY_API_URL,
        description="URL YooMoney API"
    )

class YooMoneyTokenData:
    """Данные OAuth-токена YooMoney, хранятся в Redis storage."""

    def __init__(self, token: str, obtained_at: datetime, expires_at: datetime):
        self.token: str = token
        self.obtained_at: datetime = obtained_at
        self.expires_at: datetime = expires_at

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    def to_json(self) -> str:
        return json.dumps({
            "token": self.token,
            "obtained_at": self.obtained_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        })

    @classmethod
    def from_json(cls, raw: str) -> "YooMoneyTokenData":
        data = parse_json_object(raw, "YooMoney token data")
        token = data["token"]
        obtained_at = data["obtained_at"]
        expires_at = data["expires_at"]
        if not isinstance(token, str):
            raise ValueError("YooMoney token data token must be a string")
        if not isinstance(obtained_at, str):
            raise ValueError("YooMoney token data obtained_at must be a string")
        if not isinstance(expires_at, str):
            raise ValueError("YooMoney token data expires_at must be a string")
        return cls(
            token=token,
            obtained_at=datetime.fromisoformat(obtained_at),
            expires_at=datetime.fromisoformat(expires_at),
        )


class YooMoneyWebhookPayload(StrictBaseModel):
    notification_type: str
    operation_id: str
    amount: str
    currency: str
    datetime: str
    sender: str
    codepro: str
    sha1_hash: str
    label: str


async def save_access_token(storage: Storage, token: str) -> YooMoneyTokenData:
    """Сохраняет access_token в storage с метками времени."""
    now = datetime.now(timezone.utc)
    token_data = YooMoneyTokenData(
        token=token,
        obtained_at=now,
        expires_at=now + timedelta(days=365 * YOOMONEY_TOKEN_LIFETIME_YEARS),
    )
    _ = await storage.set(YOOMONEY_TOKEN_STORAGE_KEY, token_data.to_json(), force_global=True)
    logger.info("YooMoney access_token сохранён в storage, истекает %s", token_data.expires_at.isoformat())
    return token_data

async def load_access_token(storage: Storage) -> YooMoneyTokenData | None:
    """Загружает access_token из storage. Возвращает None если токена нет."""
    raw = await storage.get(YOOMONEY_TOKEN_STORAGE_KEY, force_global=True)
    if not raw:
        return None
    token_data = YooMoneyTokenData.from_json(raw)
    if token_data.is_expired():
        logger.warning("YooMoney access_token истёк (%s), требуется повторная OAuth-авторизация", token_data.expires_at)
        return None
    return token_data

class YooMoneyProvider(BasePaymentProvider[YooMoneyConfig]):
    """
    Провайдер для YooMoney (Quickpay).

    Документация: https://yoomoney.ru/docs/wallet
    """

    def __init__(self, config: YooMoneyConfig):
        super().__init__(config)
        self._access_token: str | None = None
        logger.info("Инициализирован YooMoney провайдер: кошелек=%s", config.account_number)

    def set_access_token(self, token: str) -> None:
        normalized = token.strip()
        if normalized == "":
            raise ValueError("YooMoney access_token must be a non-empty string")
        self._access_token = normalized

    async def _get_access_token(self, storage: Storage) -> str:
        """Получает access_token из storage. Raise если нет."""
        if self._access_token:
            return self._access_token

        token_data = await load_access_token(storage)
        if not token_data:
            raise ValueError(YOOMONEY_MISSING_TOKEN_MESSAGE)
        token = (token_data.token or "").strip()
        if not token:
            raise ValueError(YOOMONEY_MISSING_TOKEN_MESSAGE)
        self._access_token = token
        return self._access_token

    @override
    async def create_payment(self, request: PaymentRequest) -> PaymentResponse:
        """Генерирует URL для YooMoney Quickpay формы."""

        logger.info(
            "Создание платежа YooMoney: сумма=%s₽, компания=%s, транзакция=%s",
            request.amount, request.company_id, request.transaction_id,
        )

        params = {
            "receiver": self.config.account_number,
            "quickpay-form": "shop",
            "targets": f"Пополнение баланса (ID: {request.transaction_id})",
            "paymentType": "AC",
            "sum": str(request.amount),
            "label": request.transaction_id,
            "successURL": request.success_url,
            "failURL": request.fail_url
        }

        payment_url = f"{self.config.quickpay_url}?{urlencode(params)}"

        logger.debug("Сгенерирован URL платежа: %s", payment_url)

        return PaymentResponse(
            payment_url=payment_url,
            external_payment_id=None,
            metadata={
                "provider": "yoomoney",
                "account_number": self.config.account_number
            }
        )

    @override
    async def verify_webhook(self, webhook_data: JsonObject) -> WebhookVerificationResult:
        """
        Проверяет подпись YooMoney HTTP-уведомления.

        Формат подписи:
        sha1(notification_type&operation_id&amount&currency&datetime&sender&codepro&notification_secret&label)
        """

        logger.info("Проверка webhook YooMoney: %s", webhook_data.get("label"))

        try:
            payload = YooMoneyWebhookPayload.model_validate(webhook_data)
        except ValidationError:
            logger.error("YooMoney webhook payload has invalid schema")
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Missing required webhook field or invalid payload",
            )

        signature_string = (
            f"{payload.notification_type}&"
            f"{payload.operation_id}&"
            f"{payload.amount}&"
            f"{payload.currency}&"
            f"{payload.datetime}&"
            f"{payload.sender}&"
            f"{payload.codepro}&"
            f"{self.config.notification_secret}&"
            f"{payload.label}"
        )

        expected_hash = hashlib.sha1(signature_string.encode()).hexdigest()

        is_valid = expected_hash == payload.sha1_hash

        if is_valid:
            logger.info("Webhook валиден: транзакция=%s, сумма=%s", payload.label, payload.amount)
        else:
            logger.error(
                "Невалидная подпись webhook: expected=%s, received=%s",
                expected_hash,
                payload.sha1_hash,
            )

        return WebhookVerificationResult(
            is_valid=is_valid,
            transaction_id=payload.label if is_valid else None,
            amount=float(payload.amount) if is_valid else None,
            external_payment_id=payload.operation_id if is_valid else None,
            status="success" if is_valid else "unknown",
            error_message=None if is_valid else "Invalid signature"
        )

    @override
    async def check_payment_status(self, external_payment_id: str, storage: Storage | None = None) -> str:
        """
        Проверяет статус платежа через YooMoney operation-details API.
        Требует access_token.
        """
        if not storage:
            raise ValueError("storage обязателен для check_payment_status")

        access_token = await self._get_access_token(storage)

        async with get_httpx_client(timeout=30.0) as client:
            response = await client.post(
                f"{self.config.api_url}/operation-details",
                headers={"Authorization": f"Bearer {access_token}"},
                data={"operation_id": external_payment_id},
            )
            _ = response.raise_for_status()
            data = parse_json_object(response.content, "YooMoney operation-details response")

        status = data["status"]
        if not isinstance(status, str):
            raise ValueError("YooMoney operation-details status must be a string")
        logger.info("Статус платежа %s: %s", external_payment_id, status)
        return status

    @override
    async def sync_pending_transactions(
        self,
        pending_transactions: list[PaymentSyncCandidate],
        storage: Storage | None = None,
    ) -> list[PaymentSyncOperation]:
        """
        Сверяет pending транзакции через YooMoney operation-history API.

        Для каждой pending транзакции запрашивает operation-history с label=transaction_id.
        Возвращает список операций со status=success.

        Документация: https://yoomoney.ru/docs/wallet/user-account/operation-history
        """
        if not storage:
            raise ValueError("storage обязателен для sync_pending_transactions")

        access_token = await self._get_access_token(storage)

        found: list[PaymentSyncOperation] = []

        for txn in pending_transactions:
            transaction_id = txn.transaction_id.strip()
            if transaction_id == "":
                raise ValueError("pending transaction_id must be a non-empty string")

            async with get_httpx_client(timeout=30.0) as client:
                response = await client.post(
                    f"{self.config.api_url}/operation-history",
                    headers={"Authorization": f"Bearer {access_token}"},
                    data={
                        "type": "deposition",
                        "label": transaction_id,
                        "records": "1",
                    },
                )
                _ = response.raise_for_status()
                data = parse_json_object(response.content, "YooMoney operation-history response")

            operations_value = data.get("operations")
            if not isinstance(operations_value, list):
                raise ValueError("YooMoney operation-history operations must be a list")

            for op in operations_value:
                op_data = require_json_object(op, "YooMoney operation")
                if op_data.get("status") == "success":
                    operation_id = op_data.get("operation_id")
                    if operation_id is not None and not isinstance(operation_id, str):
                        raise ValueError("YooMoney operation_id must be a string")
                    amount = op_data.get("amount")
                    if isinstance(amount, int | float) and not isinstance(amount, bool):
                        operation_amount = float(amount)
                    elif isinstance(amount, str) and amount.strip() != "":
                        operation_amount = float(amount)
                    elif amount is None:
                        operation_amount = None
                    else:
                        raise ValueError("YooMoney operation amount must be number, string or null")
                    found.append(
                        PaymentSyncOperation(
                            transaction_id=transaction_id,
                            operation_id=operation_id,
                            amount=operation_amount,
                            status=PaymentStatus.SUCCESS,
                        )
                    )
                    logger.info(
                        "Сверка: найдена оплаченная транзакция %s (operation_id=%s)",
                        transaction_id,
                        operation_id,
                    )
                    break

        return found
