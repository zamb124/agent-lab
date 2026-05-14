"""
Подстройка времени для SigV4 под HTTP Date ответа S3-совместимого сервера.

Устраняет RequestTimeTooSkewed, когда часы ОС клиента расходятся с временем
на стороне MinIO (Docker VM / удалённый хост), без ручного NTP на каждой машине.

Один глобальный сдвиг на процесс. В botocore get_current_datetime импортируется
в auth/signers/endpoint и др. как локальное имя; патчить нужно каждый такой модуль,
иначе SigV4 всё ещё подписывается «локальными» часами.

Не подходит для одновременной работы с двумя S3 endpoint с сильно разным временем.
"""

from __future__ import annotations

import datetime
import ssl
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.logging import get_logger

logger = get_logger(__name__)
_clock_patch_applied: bool = False
_original_get_current_datetime: Optional[object] = None

def _read_date_header(req: Request) -> Optional[str]:
    ctx = ssl.create_default_context()
    try:
        with urlopen(req, timeout=8, context=ctx) as resp:
            return resp.headers.get("Date")
    except HTTPError as exc:
        return exc.headers.get("Date")
    except (URLError, OSError, TimeoutError):
        return None

def _http_date_for_endpoint(base_url: str) -> Optional[str]:
    b = base_url.strip().rstrip("/")
    attempts: list[tuple[str, str]] = [
        (f"{b}/minio/health/live", "GET"),
        (f"{b}/", "HEAD"),
    ]
    for url, method in attempts:
        req = Request(url, method=method)
        date_hdr = _read_date_header(req)
        if date_hdr:
            return date_hdr
    return None

def _apply_process_wide_offset(offset: datetime.timedelta) -> None:
    global _clock_patch_applied, _original_get_current_datetime
    if _clock_patch_applied:
        return

    import botocore.compat as bc

    _original_get_current_datetime = bc.get_current_datetime

    def _patched_get_current_datetime(remove_tzinfo: bool = True) -> datetime.datetime:
        if _original_get_current_datetime is None:
            raise RuntimeError("s3_sigv4_clock: потерян оригинал get_current_datetime")
        base = _original_get_current_datetime(remove_tzinfo=remove_tzinfo)
        return base + offset

    bc.get_current_datetime = _patched_get_current_datetime

    for name in (
        "botocore.auth",
        "botocore.signers",
        "botocore.endpoint",
        "botocore.utils",
    ):
        mod = __import__(name, fromlist=["*"])
        if hasattr(mod, "get_current_datetime"):
            mod.get_current_datetime = _patched_get_current_datetime

    try:
        crt_auth = __import__("botocore.crt.auth", fromlist=["*"])
    except ImportError:
        pass
    else:
        if hasattr(crt_auth, "get_current_datetime"):
            crt_auth.get_current_datetime = _patched_get_current_datetime

    _clock_patch_applied = True
    logger.info(
        "SigV4: сдвиг времени относительно HTTP Date S3 endpoint: %s",
        offset,
    )

def ensure_sigv4_clock_aligned_with_endpoint(endpoint_url: str | None) -> None:
    """
    Синхронизирует время подписи SigV4 с сервером по заголовку Date (без AWS-подписи).

    Вызывать при создании S3-клиента, если задан custom endpoint_url (MinIO, VK, Yandex).
    """
    global _clock_patch_applied
    if _clock_patch_applied:
        return
    if endpoint_url is None:
        return
    raw = str(endpoint_url).strip()
    if raw == "":
        return

    date_hdr = _http_date_for_endpoint(raw)
    if not date_hdr:
        logger.warning(
            "SigV4 clock sync: не получен HTTP Date с %s — подпись по локальным часам",
            raw,
        )
        return

    try:
        server_dt = parsedate_to_datetime(date_hdr)
    except (TypeError, ValueError) as exc:
        logger.warning("SigV4 clock sync: не разобрали Date %r: %s", date_hdr, exc)
        return

    if server_dt.tzinfo is not None:
        server_utc_naive = server_dt.astimezone(datetime.timezone.utc).replace(
            tzinfo=None
        )
    else:
        server_utc_naive = server_dt

    local_utc_naive = datetime.datetime.now(datetime.timezone.utc).replace(
        tzinfo=None
    )
    offset = server_utc_naive - local_utc_naive

    if abs(offset.total_seconds()) < 2.0:
        logger.debug("SigV4 clock sync: |offset| < 2s, патч не нужен")
        return

    _apply_process_wide_offset(offset)
