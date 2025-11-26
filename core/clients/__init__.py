"""
Clients - клиенты для внешних сервисов.
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
]
