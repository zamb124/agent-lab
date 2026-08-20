"""Корень НУЦ Минцифры для TLS Tinkoff: отпечаток официального файла."""

from hashlib import sha256
from ssl import CERT_REQUIRED, PEM_cert_to_DER_cert

from core.clients.payment.tinkoff_ssl import (
    RUSSIAN_TRUSTED_ROOT_CA_DER_SHA256,
    russian_trusted_root_ca_pem,
    tinkoff_ssl_context,
)


def test_russian_trusted_root_ca_official_fingerprint() -> None:
    pem = russian_trusted_root_ca_pem()
    assert "BEGIN CERTIFICATE" in pem
    assert sha256(PEM_cert_to_DER_cert(pem)).hexdigest() == RUSSIAN_TRUSTED_ROOT_CA_DER_SHA256


def test_tinkoff_ssl_context_requires_verify() -> None:
    context = tinkoff_ssl_context()
    assert context.verify_mode == CERT_REQUIRED
