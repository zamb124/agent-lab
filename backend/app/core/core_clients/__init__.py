"""
Клиенты для внешних сервисов.
"""

from .s3_client import S3Client, S3ClientFactory, get_default_s3_client, close_default_s3_client
from .cloud_voice_client import (
    CloudVoiceClient,
    CloudVoiceClientFactory,
    get_default_cloud_voice_client,
    close_default_cloud_voice_client,
)

__all__ = [
    "S3Client",
    "S3ClientFactory", 
    "get_default_s3_client",
    "close_default_s3_client",
    "CloudVoiceClient",
    "CloudVoiceClientFactory",
    "get_default_cloud_voice_client",
    "close_default_cloud_voice_client",
]
