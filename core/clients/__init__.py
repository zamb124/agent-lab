"""
Clients - клиенты для внешних сервисов и межсервисного взаимодействия.
"""

from core.clients.nano_banana import NanoBananaClient, NanoBananaClientFactory
from core.clients.cloud_voice import CloudVoiceClient, CloudVoiceClientFactory
from core.clients.llm.factory import get_llm
from core.clients.payment import (
    BasePaymentProvider,
    PaymentProviderFactory,
    YooMoneyProvider,
    YuKassaProvider,
    PaymentRequest,
    PaymentResponse,
)
from core.clients.service_client import (
    ServiceClient,
    ServiceClientError,
    ServiceValidationError,
    get_service_client,
    init_service_client,
    shutdown_service_client,
)

__all__ = [
    "NanoBananaClient",
    "NanoBananaClientFactory",
    "CloudVoiceClient",
    "CloudVoiceClientFactory",
    "get_llm",
    "BasePaymentProvider",
    "PaymentProviderFactory",
    "YooMoneyProvider",
    "YuKassaProvider",
    "PaymentRequest",
    "PaymentResponse",
    "ServiceClient",
    "ServiceClientError",
    "ServiceValidationError",
    "get_service_client",
    "init_service_client",
    "shutdown_service_client",
]
