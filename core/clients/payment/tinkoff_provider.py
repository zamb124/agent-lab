"""Провайдер интернет-эквайринга Т-Банка: платёжная форма банка (nonPCI)."""

from typing import Literal, override

from pydantic import Field

from core.clients.payment.base_provider import (
    BasePaymentProvider,
    PaymentProviderConfig,
    PaymentRequest,
    PaymentResponse,
    WebhookVerificationResult,
)
from core.clients.payment.tinkoff_ssl import tinkoff_ssl_context
from core.clients.payment.tinkoff_token import (
    TINKOFF_ORDER_ID_MAX_LEN,
    compute_tinkoff_token,
    kopecks_to_rubles,
    rubles_to_kopecks,
)
from core.db.storage import Storage
from core.http import get_httpx_client
from core.logging import get_logger
from core.models.payment_models import (
    PaymentStatus,
    PaymentSyncCandidate,
    PaymentSyncOperation,
)
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

logger = get_logger(__name__)

TINKOFF_API_URL = "https://securepay.tinkoff.ru/v2"
TinkoffTaxation = Literal["osn", "usn_income", "usn_income_outcome", "esn", "patent"]

TINKOFF_CONFIRMED = "CONFIRMED"
TINKOFF_PENDING_STATUSES = frozenset(
    {
        "NEW",
        "FORM_SHOWED",
        "AUTHORIZING",
        "3DS_CHECKING",
        "3DS_CHECKED",
        "AUTHORIZED",
        "CONFIRMING",
    }
)
TINKOFF_FAILED_STATUSES = frozenset(
    {
        "REJECTED",
        "AUTH_FAIL",
        "DEADLINE_EXPIRED",
        "CANCELED",
        "CANCELLED",
    }
)
TINKOFF_REFUNDED_STATUSES = frozenset(
    {
        "REFUNDED",
        "PARTIAL_REFUNDED",
        "REVERSED",
        "PARTIAL_REVERSED",
    }
)


class TinkoffConfig(PaymentProviderConfig[Literal["tinkoff"]]):
    provider_type: Literal["tinkoff"] = "tinkoff"
    terminal_key: str = Field(description="TerminalKey терминала Т-Банка")
    password: str = Field(description="Пароль терминала для Token")
    api_url: str = Field(default=TINKOFF_API_URL, description="Базовый URL eacq API /v2")
    receipt_enabled: bool = Field(
        default=True,
        description="Передавать Receipt в Init (нужна онлайн-касса на терминале)",
    )
    taxation: TinkoffTaxation = Field(
        default="usn_income_outcome",
        description="СНО чека 54-ФЗ. АУСН доходы минус расходы — usn_income_outcome",
    )


def _require_str(value: JsonValue, field_name: str) -> str:
    if isinstance(value, str) and value.strip() != "":
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    raise ValueError(f"{field_name} must be a non-empty string")


def _require_int(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip() != "":
        return int(value)
    raise ValueError(f"{field_name} must be an integer")


def _require_bool(value: JsonValue, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a boolean")


def _platform_status(bank_status: str) -> str:
    if bank_status == TINKOFF_CONFIRMED:
        return PaymentStatus.SUCCESS.value
    if bank_status in TINKOFF_PENDING_STATUSES:
        return PaymentStatus.PENDING.value
    if bank_status in TINKOFF_FAILED_STATUSES:
        return PaymentStatus.FAILED.value
    if bank_status in TINKOFF_REFUNDED_STATUSES:
        return PaymentStatus.REFUNDED.value
    raise ValueError(f"unknown Tinkoff payment status: {bank_status}")


def _check_order_terminal_operations(
    *,
    transaction_id: str,
    payments: list[JsonValue],
) -> list[PaymentSyncOperation]:
    found: list[PaymentSyncOperation] = []
    for payment in payments:
        payment_object = require_json_object(payment, "Tinkoff CheckOrder payment")
        bank_status = _require_str(payment_object["Status"], "Payments.Status")
        platform_status = PaymentStatus(_platform_status(bank_status))
        if platform_status == PaymentStatus.PENDING:
            continue
        payment_id = _require_str(payment_object["PaymentId"], "Payments.PaymentId")
        amount_kopecks = _require_int(payment_object["Amount"], "Payments.Amount")
        found.append(
            PaymentSyncOperation(
                transaction_id=transaction_id,
                status=platform_status,
                operation_id=payment_id,
                amount=kopecks_to_rubles(amount_kopecks),
            )
        )
        break
    return found


class TinkoffProvider(BasePaymentProvider[TinkoffConfig]):
    def __init__(self, config: TinkoffConfig):
        super().__init__(config)
        if config.terminal_key.strip() == "":
            raise ValueError("tinkoff terminal_key is required")
        if config.password.strip() == "":
            raise ValueError("tinkoff terminal password is required")
        if config.api_url.strip() == "":
            raise ValueError("tinkoff api_url is required")
        logger.info(
            "payments.tinkoff_provider_initialized",
            terminal_key=config.terminal_key,
        )

    def _endpoint(self, method: str) -> str:
        return f"{self.config.api_url.rstrip('/')}/{method}"

    def _signed_body(self, fields: JsonObject) -> JsonObject:
        signed: JsonObject = dict(fields)
        signed["Token"] = compute_tinkoff_token(fields, self.config.password)
        return signed

    async def _post_json(self, method: str, fields: JsonObject) -> JsonObject:
        signed = self._signed_body(fields)
        async with get_httpx_client(timeout=30.0, verify=tinkoff_ssl_context()) as client:
            response = await client.post(self._endpoint(method), json=signed)
            _ = response.raise_for_status()
            return parse_json_object(response.content, f"Tinkoff {method} response")

    def _receipt(self, *, amount_kopecks: int, customer_email: str) -> JsonObject:
        email = customer_email.strip()
        if email == "":
            raise ValueError("customer_email is required when Tinkoff receipt_enabled is true")
        return {
            "Email": email,
            "Taxation": self.config.taxation,
            "Items": [
                {
                    "Name": "Пополнение баланса",
                    "Price": amount_kopecks,
                    "Quantity": 1,
                    "Amount": amount_kopecks,
                    "Tax": "none",
                    "PaymentMethod": "full_prepayment",
                    "PaymentObject": "service",
                }
            ],
        }

    @override
    async def create_payment(self, request: PaymentRequest) -> PaymentResponse:
        amount_kopecks = rubles_to_kopecks(request.amount)
        language = request.language.strip()
        if language == "":
            raise ValueError("language is required")
        notification_url = request.notification_url.strip()
        if notification_url == "":
            raise ValueError("notification_url is required")
        order_id = request.transaction_id.strip()
        if order_id == "":
            raise ValueError("transaction_id is required")
        if len(order_id) > TINKOFF_ORDER_ID_MAX_LEN:
            raise ValueError(
                f"Tinkoff OrderId length {len(order_id)} exceeds {TINKOFF_ORDER_ID_MAX_LEN}"
            )
        body: JsonObject = {
            "TerminalKey": self.config.terminal_key,
            "Amount": amount_kopecks,
            "OrderId": order_id,
            "Description": "Пополнение баланса",
            "PayType": "O",
            "Language": language,
            "NotificationURL": notification_url,
            "SuccessURL": request.success_url,
            "FailURL": request.fail_url,
            "DATA": {
                "OperationInitiatorType": "0",
            },
        }
        if self.config.receipt_enabled:
            customer_email = request.customer_email
            if customer_email is None:
                raise ValueError("customer_email is required when Tinkoff receipt_enabled is true")
            body["Receipt"] = self._receipt(
                amount_kopecks=amount_kopecks,
                customer_email=customer_email,
            )

        logger.info(
            "payments.tinkoff_init_requested",
            company_id=request.company_id,
            transaction_id=request.transaction_id,
            amount_kopecks=amount_kopecks,
            notification_url=request.notification_url,
        )
        data = await self._post_json("Init", body)
        success = _require_bool(data["Success"], "Init.Success")
        if not success:
            error_code = data.get("ErrorCode")
            message = data.get("Message")
            details = data.get("Details")
            raise ValueError(
                "Tinkoff Init failed: "
                + f"ErrorCode={error_code} Message={message} Details={details}"
            )
        payment_url = data.get("PaymentURL")
        if not isinstance(payment_url, str) or payment_url.strip() == "":
            raise ValueError("Tinkoff Init response missing PaymentURL")
        payment_id = _require_str(data["PaymentId"], "Init.PaymentId")
        return PaymentResponse(
            payment_url=payment_url,
            external_payment_id=payment_id,
            metadata={
                "provider": "tinkoff",
                "terminal_key": self.config.terminal_key,
            },
        )

    @override
    async def verify_webhook(self, webhook_data: JsonObject) -> WebhookVerificationResult:
        token_value = webhook_data.get("Token")
        if not isinstance(token_value, str) or token_value.strip() == "":
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Tinkoff webhook missing Token",
            )
        expected = compute_tinkoff_token(webhook_data, self.config.password)
        if expected != token_value:
            logger.error(
                "payments.tinkoff_webhook_token_mismatch",
                expected_prefix=expected[:12],
                received_prefix=token_value[:12],
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Invalid Tinkoff webhook Token",
            )
        terminal_key = _require_str(webhook_data["TerminalKey"], "TerminalKey")
        if terminal_key != self.config.terminal_key:
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Tinkoff webhook TerminalKey mismatch",
            )
        order_id = _require_str(webhook_data["OrderId"], "OrderId")
        payment_id = _require_str(webhook_data["PaymentId"], "PaymentId")
        amount_kopecks = _require_int(webhook_data["Amount"], "Amount")
        bank_status = _require_str(webhook_data["Status"], "Status")
        return WebhookVerificationResult(
            is_valid=True,
            transaction_id=order_id,
            amount=kopecks_to_rubles(amount_kopecks),
            external_payment_id=payment_id,
            status=_platform_status(bank_status),
        )

    @override
    async def check_payment_status(self, external_payment_id: str) -> str:
        payment_id = external_payment_id.strip()
        if payment_id == "":
            raise ValueError("external_payment_id is required")
        data = await self._post_json(
            "GetState",
            {
                "TerminalKey": self.config.terminal_key,
                "PaymentId": payment_id,
            },
        )
        success = _require_bool(data["Success"], "GetState.Success")
        if not success:
            raise ValueError(
                "Tinkoff GetState failed: "
                + f"ErrorCode={data.get('ErrorCode')} Message={data.get('Message')}"
            )
        return _require_str(data["Status"], "GetState.Status")

    async def cancel_payment(
        self,
        payment_id: str,
        *,
        amount: float,
        customer_email: str | None,
    ) -> str:
        clean_payment_id = payment_id.strip()
        if clean_payment_id == "":
            raise ValueError("payment_id is required")
        amount_kopecks = rubles_to_kopecks(amount)
        fields: JsonObject = {
            "TerminalKey": self.config.terminal_key,
            "PaymentId": clean_payment_id,
        }
        if self.config.receipt_enabled:
            if customer_email is None:
                raise ValueError("customer_email is required when Tinkoff receipt_enabled is true")
            fields["Receipt"] = self._receipt(
                amount_kopecks=amount_kopecks,
                customer_email=customer_email,
            )
        data = await self._post_json("Cancel", fields)
        success = _require_bool(data["Success"], "Cancel.Success")
        if not success:
            error_code = data.get("ErrorCode")
            message = data.get("Message")
            details = data.get("Details")
            raise ValueError(
                "Tinkoff Cancel failed: "
                + f"ErrorCode={error_code} Message={message} Details={details}"
            )
        bank_status = _require_str(data["Status"], "Cancel.Status")
        logger.info(
            "payments.tinkoff_cancel_succeeded",
            payment_id=clean_payment_id,
            status=bank_status,
        )
        return bank_status

    @override
    async def sync_pending_transactions(
        self,
        pending_transactions: list[PaymentSyncCandidate],
        storage: Storage | None = None,
    ) -> list[PaymentSyncOperation]:
        _ = storage
        found: list[PaymentSyncOperation] = []
        for txn in pending_transactions:
            transaction_id = txn.transaction_id.strip()
            if transaction_id == "":
                raise ValueError("pending transaction_id must be a non-empty string")
            data = await self._post_json(
                "CheckOrder",
                {
                    "TerminalKey": self.config.terminal_key,
                    "OrderId": transaction_id,
                },
            )
            success = _require_bool(data["Success"], "CheckOrder.Success")
            if not success:
                logger.warning(
                    "payments.tinkoff_check_order_failed",
                    transaction_id=transaction_id,
                    error_code=data.get("ErrorCode"),
                    message=data.get("Message"),
                )
                continue
            payments_value = data.get("Payments")
            if payments_value is None:
                continue
            if not isinstance(payments_value, list):
                raise ValueError("Tinkoff CheckOrder Payments must be a list")
            found.extend(
                _check_order_terminal_operations(
                    transaction_id=transaction_id,
                    payments=payments_value,
                )
            )
        return found
