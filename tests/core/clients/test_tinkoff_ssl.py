"""CA НУЦ Минцифры для TLS Tinkoff: pin, цепочка, fail-closed, живой handshake."""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from socket import create_connection
from ssl import (
    CERT_REQUIRED,
    PROTOCOL_TLS_CLIENT,
    PEM_cert_to_DER_cert,
    SSLCertVerificationError,
    SSLContext,
    create_default_context,
)

import certifi
import pytest

from core.clients.payment import tinkoff_ssl
from core.clients.payment.tinkoff_provider import TinkoffProvider
from core.clients.payment.tinkoff_ssl import (
    RUSSIAN_TRUSTED_ROOT_CA_DER_SHA256,
    RUSSIAN_TRUSTED_SUB_CA_DER_SHA256,
    russian_trusted_root_ca_pem,
    russian_trusted_sub_ca_pem,
    tinkoff_ssl_context,
)
from core.http import ProxyStrategy, get_httpx_client

_TBANK_MINCIFRY_PROBE_HOST = "mddc.tbank.ru"
_TBANK_MINCIFRY_PROBE_URL = "https://mddc.tbank.ru/"
_ROOT_CN = "Russian Trusted Root CA"
_SUB_CN = "Russian Trusted Sub CA"
_ROOT_SERIAL = "1000"
_SUB_SERIAL = "1002"

_CA_PEM_LOADERS: tuple[tuple[str, Callable[[], str], str], ...] = (
    (
        "_RUSSIAN_TRUSTED_ROOT_CA_PATH",
        russian_trusted_root_ca_pem,
        RUSSIAN_TRUSTED_ROOT_CA_DER_SHA256,
    ),
    (
        "_RUSSIAN_TRUSTED_SUB_CA_PATH",
        russian_trusted_sub_ca_pem,
        RUSSIAN_TRUSTED_SUB_CA_DER_SHA256,
    ),
)


def _certificate_common_name(name: object) -> str:
    if not isinstance(name, tuple):
        raise AssertionError("certificate name must be a tuple")
    for rdn in name:
        if not isinstance(rdn, tuple):
            raise AssertionError("RDN must be a tuple")
        for attribute in rdn:
            if not isinstance(attribute, tuple) or len(attribute) != 2:
                raise AssertionError("attribute must be a pair")
            key, value = attribute
            if key != "commonName":
                continue
            if not isinstance(value, str) or value.strip() == "":
                raise AssertionError("commonName must be a non-empty string")
            return value
    raise AssertionError("commonName is required")


def _single_ca_record(pem: str) -> Mapping[str, object]:
    isolated = SSLContext(PROTOCOL_TLS_CLIENT)
    isolated.load_verify_locations(cadata=pem)
    records = isolated.get_ca_certs()
    if len(records) != 1:
        raise AssertionError(f"expected exactly one CA record, got {len(records)}")
    return records[0]


def _ssl_not_after(value: object) -> datetime:
    if not isinstance(value, str) or value.strip() == "":
        raise AssertionError("notAfter must be a non-empty string")
    if not value.endswith(" GMT"):
        raise AssertionError(f"notAfter must be GMT: {value}")
    parsed = datetime.strptime(value, "%b %d %H:%M:%S %Y GMT")
    return parsed.replace(tzinfo=timezone.utc)


def _tls_peer_certificate(host: str, context: SSLContext) -> Mapping[str, object]:
    with create_connection((host, 443), timeout=15.0) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            peer = tls.getpeercert()
    if not isinstance(peer, dict) or len(peer) == 0:
        raise AssertionError("peer certificate is required after TLS handshake")
    return peer


def _assert_single_official_pem(pem: str, expected_sha256: str) -> None:
    assert pem.startswith("-----BEGIN CERTIFICATE-----\n")
    assert pem.rstrip("\n").endswith("-----END CERTIFICATE-----")
    assert pem.count("-----BEGIN CERTIFICATE-----") == 1
    assert pem.count("-----END CERTIFICATE-----") == 1
    assert sha256(PEM_cert_to_DER_cert(pem)).hexdigest() == expected_sha256


@pytest.mark.parametrize(
    ("loader", "expected_sha256"),
    [
        (russian_trusted_root_ca_pem, RUSSIAN_TRUSTED_ROOT_CA_DER_SHA256),
        (russian_trusted_sub_ca_pem, RUSSIAN_TRUSTED_SUB_CA_DER_SHA256),
    ],
)
def test_official_ca_pem_is_single_pinned_certificate(
    loader: Callable[[], str],
    expected_sha256: str,
) -> None:
    _assert_single_official_pem(loader(), expected_sha256)


def test_official_ca_files_match_pinned_loaders() -> None:
    certs_dir = Path(tinkoff_ssl.__file__).resolve().parent / "certs"
    root_path = certs_dir / "russian_trusted_root_ca.pem"
    sub_path = certs_dir / "russian_trusted_sub_ca.pem"
    assert root_path.read_text() == russian_trusted_root_ca_pem()
    assert sub_path.read_text() == russian_trusted_sub_ca_pem()


def test_root_ca_identity_and_self_issued() -> None:
    record = _single_ca_record(russian_trusted_root_ca_pem())
    assert _certificate_common_name(record["subject"]) == _ROOT_CN
    assert _certificate_common_name(record["issuer"]) == _ROOT_CN
    assert record["serialNumber"] == _ROOT_SERIAL
    assert _ssl_not_after(record["notAfter"]) > datetime.now(timezone.utc)


def test_sub_ca_issued_by_root_and_not_expired() -> None:
    record = _single_ca_record(russian_trusted_sub_ca_pem())
    assert _certificate_common_name(record["subject"]) == _SUB_CN
    assert _certificate_common_name(record["issuer"]) == _ROOT_CN
    assert record["serialNumber"] == _SUB_SERIAL
    assert _ssl_not_after(record["notAfter"]) > datetime.now(timezone.utc)


def test_tinkoff_ssl_context_requires_hostname_and_peer_verify() -> None:
    context = tinkoff_ssl_context()
    assert context.verify_mode == CERT_REQUIRED
    assert context.check_hostname is True


def test_tinkoff_ssl_context_contains_exact_mincifry_der_pins() -> None:
    context = tinkoff_ssl_context()
    loaded_digests = {
        sha256(der).hexdigest() for der in context.get_ca_certs(binary_form=True)
    }
    assert RUSSIAN_TRUSTED_ROOT_CA_DER_SHA256 in loaded_digests
    assert RUSSIAN_TRUSTED_SUB_CA_DER_SHA256 in loaded_digests


def test_certifi_bundle_does_not_contain_mincifry_pins() -> None:
    mozilla = create_default_context(cafile=certifi.where())
    mozilla_digests = {
        sha256(der).hexdigest() for der in mozilla.get_ca_certs(binary_form=True)
    }
    assert RUSSIAN_TRUSTED_ROOT_CA_DER_SHA256 not in mozilla_digests
    assert RUSSIAN_TRUSTED_SUB_CA_DER_SHA256 not in mozilla_digests


@pytest.mark.parametrize(("path_attr", "loader", "_expected"), _CA_PEM_LOADERS)
def test_pinned_ca_missing_file_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path_attr: str,
    loader: Callable[[], str],
    _expected: str,
) -> None:
    missing = tmp_path / "absent.pem"
    monkeypatch.setattr(tinkoff_ssl, path_attr, missing)
    with pytest.raises(FileNotFoundError, match="Tinkoff TLS CA is missing"):
        loader()


@pytest.mark.parametrize(("path_attr", "loader", "expected_sha256"), _CA_PEM_LOADERS)
def test_pinned_ca_swapped_official_pem_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path_attr: str,
    loader: Callable[[], str],
    expected_sha256: str,
) -> None:
    swapped = (
        russian_trusted_sub_ca_pem()
        if expected_sha256 == RUSSIAN_TRUSTED_ROOT_CA_DER_SHA256
        else russian_trusted_root_ca_pem()
    )
    swapped_digest = sha256(PEM_cert_to_DER_cert(swapped)).hexdigest()
    assert swapped_digest != expected_sha256
    tampered = tmp_path / "tampered.pem"
    tampered.write_text(swapped)
    monkeypatch.setattr(tinkoff_ssl, path_attr, tampered)
    with pytest.raises(ValueError, match=f"fingerprint mismatch: {swapped_digest}"):
        loader()


def test_tinkoff_provider_post_uses_tinkoff_ssl_context() -> None:
    source = getsource(TinkoffProvider._post_json)
    assert "verify=tinkoff_ssl_context()" in source
    assert "verify=False" not in getsource(TinkoffProvider)
    assert "verify=True" not in source


@pytest.mark.network
@pytest.mark.timeout(30)
def test_certifi_alone_rejects_mddc_tbank_handshake() -> None:
    mozilla = create_default_context(cafile=certifi.where())
    with pytest.raises(SSLCertVerificationError):
        _tls_peer_certificate(_TBANK_MINCIFRY_PROBE_HOST, mozilla)


@pytest.mark.network
@pytest.mark.timeout(30)
def test_tinkoff_ssl_context_accepts_mddc_tbank_mincifry_issuer() -> None:
    peer = _tls_peer_certificate(_TBANK_MINCIFRY_PROBE_HOST, tinkoff_ssl_context())
    issuer_cn = _certificate_common_name(peer["issuer"])
    assert issuer_cn in {_SUB_CN, _ROOT_CN}


@pytest.mark.network
@pytest.mark.timeout(30)
async def test_tinkoff_httpx_client_trusts_mddc_tbank() -> None:
    async with get_httpx_client(
        timeout=15.0,
        verify=tinkoff_ssl_context(),
        strategy=ProxyStrategy.DIRECT_ONLY,
    ) as client:
        response = await client.get(_TBANK_MINCIFRY_PROBE_URL)
    assert response.status_code >= 100
    assert response.url.host == _TBANK_MINCIFRY_PROBE_HOST
