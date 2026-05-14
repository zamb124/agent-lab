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
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlencode

from pydantic import Field

from core.clients.payment.base_provider import (
    BasePaymentProvider,
    PaymentProviderConfig,
    PaymentRequest,
    PaymentResponse,
    WebhookVerificationResult,
)
from core.http import get_httpx_client
from core.logging import get_logger

logger = get_logger(__name__)
YOOMONEY_TOKEN_LIFETIME_YEARS = 3
YOOMONEY_TOKEN_STORAGE_KEY = "yoomoney:access_token"
YOOMONEY_OAUTH_AUTHORIZE_URL = "https://yoomoney.ru/oauth/authorize"
YOOMONEY_OAUTH_TOKEN_URL = "https://yoomoney.ru/oauth/token"

class YooMoneyConfig(PaymentProviderConfig):
    """Конфигурация YooMoney провайдера"""
    provider_type: Literal["yoomoney"] = "yoomoney"
    account_number: str = Field(description="Номер кошелька YooMoney")
    notification_secret: str = Field(description="Секрет для проверки HTTP-уведомлений")
    quickpay_url: str = Field(
        default="https://yoomoney.ru/quickpay/confirm.xml",
        description="URL формы оплаты Quickpay"
    )
    client_id: Optional[str] = Field(default=None, description="OAuth client_id приложения")
    client_secret: Optional[str] = Field(default=None, description="OAuth client_secret приложения")
    access_token: Optional[str] = Field(default=None, description="OAuth access_token (из env, загружается в storage при старте)")
    api_url: str = Field(
        default="https://yoomoney.ru/api",
        description="URL YooMoney API"
    )

class YooMoneyTokenData:
    """Данные OAuth-токена YooMoney, хранятся в Redis storage."""

    def __init__(self, token: str, obtained_at: datetime, expires_at: datetime):
        self.token = token
        self.obtained_at = obtained_at
        self.expires_at = expires_at

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
        data = json.loads(raw)
        return cls(
            token=data["token"],
            obtained_at=datetime.fromisoformat(data["obtained_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )

async def save_access_token(storage: Any, token: str) -> YooMoneyTokenData:
    """Сохраняет access_token в storage с метками времени."""
    now = datetime.now(timezone.utc)
    token_data = YooMoneyTokenData(
        token=token,
        obtained_at=now,
        expires_at=now + timedelta(days=365 * YOOMONEY_TOKEN_LIFETIME_YEARS),
    )
    await storage.set(YOOMONEY_TOKEN_STORAGE_KEY, token_data.to_json(), force_global=True)
    logger.info("YooMoney access_token сохранён в storage, истекает %s", token_data.expires_at.isoformat())
    return token_data

async def load_access_token(storage: Any) -> Optional[YooMoneyTokenData]:
    """Загружает access_token из storage. Возвращает None если токена нет."""
    raw = await storage.get(YOOMONEY_TOKEN_STORAGE_KEY, force_global=True)
    if not raw:
        return None
    token_data = YooMoneyTokenData.from_json(raw)
    if token_data.is_expired():
        logger.warning("YooMoney access_token истёк (%s), требуется повторная OAuth-авторизация", token_data.expires_at)
        return None
    return token_data

class YooMoneyProvider(BasePaymentProvider):
    """
    Провайдер для YooMoney (Quickpay).

    Документация: https://yoomoney.ru/docs/wallet
    """

    def __init__(self, config: YooMoneyConfig):
        super().__init__(config)
        self.config: YooMoneyConfig = config
        self._access_token: Optional[str] = None
        logger.info("Инициализирован YooMoney провайдер: кошелек=%s", config.account_number)

    async def _get_access_token(self, storage: Any) -> str:
        """Получает access_token из storage. Raise если нет."""
        if self._access_token:
            return self._access_token

        token_data = await load_access_token(storage)
        if not token_data:
            raise ValueError(
                "YooMoney access_token не найден или истёк. "
                "Выполните OAuth-авторизацию через /api/billing/yoomoney/authorize"
            )
        token = (token_data.token or "").strip()
        if not token:
            raise ValueError(
                "YooMoney access_token не найден или истёк. "
                "Выполните OAuth-авторизацию через /api/billing/yoomoney/authorize"
            )
        self._access_token = token
        return self._access_token

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

    async def verify_webhook(self, webhook_data: Dict[str, Any]) -> WebhookVerificationResult:
        """
        Проверяет подпись YooMoney HTTP-уведомления.

        Формат подписи:
        sha1(notification_type&operation_id&amount&currency&datetime&sender&codepro&notification_secret&label)
        """

        logger.info("Проверка webhook YooMoney: %s", webhook_data.get('label'))

        required_fields = [
            'notification_type', 'operation_id', 'amount',
            'currency', 'datetime', 'sender', 'codepro', 'sha1_hash', 'label'
        ]

        for field in required_fields:
            if field not in webhook_data:
                logger.error("Отсутствует обязательное поле: %s", field)
                return WebhookVerificationResult(
                    is_valid=False,
                    error_message="Missing required fields"
                )

        signature_string = (
            f"{webhook_data['notification_type']}&"
            f"{webhook_data['operation_id']}&"
            f"{webhook_data['amount']}&"
            f"{webhook_data['currency']}&"
            f"{webhook_data['datetime']}&"
            f"{webhook_data['sender']}&"
            f"{webhook_data['codepro']}&"
            f"{self.config.notification_secret}&"
            f"{webhook_data['label']}"
        )

        expected_hash = hashlib.sha1(signature_string.encode()).hexdigest()
        received_hash = webhook_data['sha1_hash']

        is_valid = expected_hash == received_hash

        if is_valid:
            logger.info("Webhook валиден: транзакция=%s, сумма=%s", webhook_data['label'], webhook_data['amount'])
        else:
            logger.error("Невалидная подпись webhook: expected=%s, received=%s", expected_hash, received_hash)

        return WebhookVerificationResult(
            is_valid=is_valid,
            transaction_id=webhook_data['label'] if is_valid else None,
            amount=float(webhook_data['amount']) if is_valid else None,
            external_payment_id=webhook_data['operation_id'] if is_valid else None,
            status="success" if is_valid else "unknown",
            error_message=None if is_valid else "Invalid signature"
        )

    async def check_payment_status(self, external_payment_id: str, storage: Any = None) -> str:
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
            response.raise_for_status()
            data = response.json()

        status = data.get('status', 'unknown')
        logger.info("Статус платежа %s: %s", external_payment_id, status)
        return status

    async def sync_pending_transactions(
        self, pending_transactions: List[Dict[str, Any]], storage: Any = None,
    ) -> List[Dict[str, Any]]:
        """
        Сверяет pending транзакции через YooMoney operation-history API.

        Для каждой pending транзакции запрашивает operation-history с label=transaction_id.
        Возвращает список операций со status=success.

        Документация: https://yoomoney.ru/docs/wallet/user-account/operation-history
        """
        if not storage:
            raise ValueError("storage обязателен для sync_pending_transactions")

        access_token = await self._get_access_token(storage)

        found: List[Dict[str, Any]] = []

        for txn in pending_transactions:
            transaction_id = txn["transaction_id"]

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
                response.raise_for_status()
                data = response.json()

            operations = data.get("operations", [])

            for op in operations:
                if op.get("status") == "success":
                    found.append({
                        "transaction_id": transaction_id,
                        "operation_id": op.get("operation_id"),
                        "amount": op.get("amount"),
                        "status": "success",
                    })
                    logger.info(
                        "Сверка: найдена оплаченная транзакция %s (operation_id=%s)",
                        transaction_id, op.get("operation_id"),
                    )
                    break

        return found

