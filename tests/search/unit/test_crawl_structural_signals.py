"""Layer-0 HTML structural signal extraction."""

import pytest

from core.crawl.structural_signals import extract_structural_signals_from_html

pytestmark = pytest.mark.unit

_JSON_LD_HTML = """
<!doctype html>
<html lang="ru">
<head>
  <title>Fallback title</title>
  <meta property="og:title" content="OG Article Title" />
  <meta property="article:published_time" content="2024-03-15T10:00:00Z" />
  <meta property="article:modified_time" content="2024-03-16T12:00:00Z" />
  <meta property="article:section" content="Technology" />
  <meta property="article:tag" content="AI" />
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    "headline": "JSON-LD Headline",
    "datePublished": "2024-03-15",
    "dateModified": "2024-03-16",
    "author": {"@type": "Person", "name": "Jane Smith"},
    "publisher": {"@type": "Organization", "name": "Example News"},
    "articleSection": "Tech",
    "keywords": "machine learning, search"
  }
  </script>
</head>
<body><h1>Body</h1></body>
</html>
"""


def test_extract_structural_signals_from_json_ld():
    signals = extract_structural_signals_from_html(_JSON_LD_HTML)
    assert signals.title == "JSON-LD Headline"
    assert signals.date_published is not None
    assert signals.date_published.isoformat() == "2024-03-15"
    assert signals.date_modified is not None
    assert signals.date_modified.isoformat() == "2024-03-16"
    assert signals.author == "Jane Smith"
    assert signals.publisher == "Example News"
    assert signals.language == "ru"
    assert signals.content_type_hint == "news"
    assert "Tech" in signals.category_hints
    assert "Technology" in signals.category_hints
    assert "AI" in signals.topic_hints


def test_extract_structural_signals_empty_when_no_html_metadata():
    signals = extract_structural_signals_from_html("<html><body>No metadata</body></html>")
    assert signals.title is None
    assert signals.date_published is None
    assert signals.content_type_hint is None
