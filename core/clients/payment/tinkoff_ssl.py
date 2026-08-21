"""TLS для API Т-Банка: certifi + официальные CA НУЦ Минцифры."""

from hashlib import sha256
from pathlib import Path
from ssl import PEM_cert_to_DER_cert, SSLContext, create_default_context

import certifi

# Официальный Russian Trusted Root CA (gu-st.ru), SHA-256 DER.
RUSSIAN_TRUSTED_ROOT_CA_DER_SHA256 = (
    "d26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31"
)
# Официальный Russian Trusted Sub CA (gu-st.ru), SHA-256 DER.
RUSSIAN_TRUSTED_SUB_CA_DER_SHA256 = (
    "bbbde2103e790b999ec62bd03cf625a5a2e7c316e10afe6a490eedead8b3fd9b"
)

_CERTS_DIR = Path(__file__).resolve().parent / "certs"
_RUSSIAN_TRUSTED_ROOT_CA_PATH = _CERTS_DIR / "russian_trusted_root_ca.pem"
_RUSSIAN_TRUSTED_SUB_CA_PATH = _CERTS_DIR / "russian_trusted_sub_ca.pem"


def _pinned_ca_pem(path: Path, expected_sha256: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Tinkoff TLS CA is missing: {path}")
    pem = path.read_text()
    digest = sha256(PEM_cert_to_DER_cert(pem)).hexdigest()
    if digest != expected_sha256:
        raise ValueError(f"Tinkoff TLS CA fingerprint mismatch: {digest}")
    return pem


def russian_trusted_root_ca_pem() -> str:
    return _pinned_ca_pem(
        _RUSSIAN_TRUSTED_ROOT_CA_PATH,
        RUSSIAN_TRUSTED_ROOT_CA_DER_SHA256,
    )


def russian_trusted_sub_ca_pem() -> str:
    return _pinned_ca_pem(
        _RUSSIAN_TRUSTED_SUB_CA_PATH,
        RUSSIAN_TRUSTED_SUB_CA_DER_SHA256,
    )


def tinkoff_ssl_context() -> SSLContext:
    context = create_default_context(cafile=certifi.where())
    context.load_verify_locations(cadata=russian_trusted_root_ca_pem())
    context.load_verify_locations(cadata=russian_trusted_sub_ca_pem())
    return context
