"""Tests for trafilatura bare_extraction metadata on crawl fetch."""

from __future__ import annotations

from apps.search.services.crawl.fetch_service import _build_crawl_fetch_result

_HTML = b"""<!DOCTYPE html>
<html>
<head>
  <title>Kubernetes Ingress Guide</title>
  <meta name="description" content="How to configure ingress nginx on Kubernetes">
</head>
<body>
  <h1>Fallback H1</h1>
  <p>""" + b"Lorem ipsum dolor sit amet. " * 20 + b"""</p>
</body>
</html>"""


def test_build_crawl_fetch_result_prefers_html_title() -> None:
    markdown = "# Fallback H1\n\n" + "Lorem ipsum dolor sit amet. " * 20
    result = _build_crawl_fetch_result(
        final_url="https://habr.com/ru/articles/ingress/",
        markdown=markdown,
        min_extract_chars=50,
        fetch_transport="http",
        html_bytes=_HTML,
        content_type="text/html",
    )
    assert result.html_title == "Kubernetes Ingress Guide"
    assert result.title == "Kubernetes Ingress Guide"
    assert result.meta_description == "How to configure ingress nginx on Kubernetes"
