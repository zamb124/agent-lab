"""
Clients - клиенты для внешних сервисов и межсервисного взаимодействия.
"""

from core.clients.nano_banana import NanoBananaClient, NanoBananaClientFactory
from core.clients.stt_client import BaseSTTClient, CloudRuSTTClient, STTClientFactory
from core.clients.llm.factory import get_llm
from core.clients.redis_client import RedisClient
from core.clients.a2a_client import A2AClient, A2AClientError
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
)
from core.clients.scheduler_client import SchedulerClient
from core.clients.rag_client import RagClient

__all__ = [
    "NanoBananaClient",
    "NanoBananaClientFactory",
    "BaseSTTClient",
    "CloudRuSTTClient",
    "STTClientFactory",
    "get_llm",
    "RedisClient",
    "A2AClient",
    "A2AClientError",
    "BasePaymentProvider",
    "PaymentProviderFactory",
    "YooMoneyProvider",
    "YuKassaProvider",
    "PaymentRequest",
    "PaymentResponse",
    "ServiceClient",
    "ServiceClientError",
    "SchedulerClient",
    "RagClient",
]
