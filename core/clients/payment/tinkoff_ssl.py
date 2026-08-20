"""TLS для API Т-Банка: certifi + официальный корень НУЦ Минцифры."""

from hashlib import sha256
from pathlib import Path
from ssl import PEM_cert_to_DER_cert, SSLContext, create_default_context

import certifi

# Официальный Russian Trusted Root CA (gu-st.ru), SHA-256 DER.
RUSSIAN_TRUSTED_ROOT_CA_DER_SHA256 = (
    "d26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31"
)
_RUSSIAN_TRUSTED_ROOT_CA_PATH = (
    Path(__file__).resolve().parent / "certs" / "russian_trusted_root_ca.pem"
)


def russian_trusted_root_ca_path() -> Path:
    if not _RUSSIAN_TRUSTED_ROOT_CA_PATH.is_file():
        raise FileNotFoundError(
            f"Tinkoff TLS CA is missing: {_RUSSIAN_TRUSTED_ROOT_CA_PATH}"
        )
    return _RUSSIAN_TRUSTED_ROOT_CA_PATH


def russian_trusted_root_ca_pem() -> str:
    pem = russian_trusted_root_ca_path().read_text()
    digest = sha256(PEM_cert_to_DER_cert(pem)).hexdigest()
    if digest != RUSSIAN_TRUSTED_ROOT_CA_DER_SHA256:
        raise ValueError(f"Tinkoff TLS CA fingerprint mismatch: {digest}")
    return pem


def tinkoff_ssl_context() -> SSLContext:
    context = create_default_context(cafile=certifi.where())
    context.load_verify_locations(cadata=russian_trusted_root_ca_pem())
    return context
