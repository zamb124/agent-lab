from __future__ import annotations

from core.http.text_encoding import decode_response_body_bytes


def test_decode_response_body_bytes_cp1251_html_without_charset_declaration() -> None:
    html = (
        b"<html><head><title>VIN</title></head><body>"
        b"\xcf\xf0\xe8 \xef\xf0\xee\xe2\xe5\xf0\xea\xe5 VIN \xe4\xe0\xed\xed\xfb\xe5 \xe7\xe0\xe3\xf0\xf3\xe6\xe5\xed\xfb."
        b"</body></html>"
    )
    text = decode_response_body_bytes(html, content_type="text/html")
    assert "При проверке VIN данные загружены." in text


def test_decode_response_body_bytes_uses_content_type_charset() -> None:
    html = (
        b"<html><body>"
        b"\xcf\xf0\xe8 \xef\xf0\xee\xe2\xe5\xf0\xea\xe5 VIN."
        b"</body></html>"
    )
    text = decode_response_body_bytes(
        html,
        content_type="text/html; charset=windows-1251",
    )
    assert "При проверке VIN." in text


def test_decode_response_body_bytes_uses_meta_charset() -> None:
    html = (
        b'<html><head><meta charset="windows-1251"></head><body>'
        b"\xcf\xf0\xe8 \xef\xf0\xee\xe2\xe5\xf0\xea\xe5 VIN."
        b"</body></html>"
    )
    text = decode_response_body_bytes(html, content_type="text/html")
    assert "При проверке VIN." in text
