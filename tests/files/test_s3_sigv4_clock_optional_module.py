"""Необязательный botocore CRT не мешает подмене часов SigV4."""

from core.files.s3_sigv4_clock import _import_optional_module


def test_import_optional_module_returns_existing_module() -> None:
    module = _import_optional_module("json")
    assert module is not None
    assert module.loads('{"ok": true}') == {"ok": True}


def test_import_optional_module_missing_returns_none() -> None:
    assert _import_optional_module("botocore.crt.auth_not_installed") is None
