"""
API для скачивания SSL сертификата.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from apps.flows.di import Di
from core.logging import get_logger

router = APIRouter(tags=["certificate"])
logger = get_logger(__name__)


@router.get("/")
async def download_certificate(di: Di):
    """
    Скачать SSL сертификат для установки в браузер.

    Сертификат необходим для работы Service Worker и PWA функций
    при использовании самоподписанного сертификата.
    """
    _ = di
    cert_path = Path("/app/ssl/platform.crt")

    if not cert_path.exists():
        logger.warning("flows.ssl.cert_missing", path=str(cert_path))
        raise HTTPException(
            status_code=404,
            detail="SSL certificate not found. Contact the administrator."
        )

    logger.info("flows.ssl")

    return FileResponse(
        cert_path,
        media_type="application/x-x509-ca-cert",
        filename="platform.crt",
        headers={
            "Content-Disposition": 'attachment; filename="platform.crt"'
        }
    )

