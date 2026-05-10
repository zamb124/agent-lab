"""Валидация slug компании (субдомен)."""

from core.utils.subdomain import validate_slug


def test_validate_slug_rejects_onlyoffice() -> None:
    ok, err = validate_slug("onlyoffice")
    assert ok is False
    assert err is not None
    assert "onlyoffice" in err


def test_validate_slug_rejects_cdn() -> None:
    ok, err = validate_slug("cdn")
    assert ok is False
    assert err is not None
    assert "cdn" in err


def test_validate_slug_accepts_normal_slug() -> None:
    ok, err = validate_slug("acme-corp")
    assert ok is True
    assert err is None
