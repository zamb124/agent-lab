"""Tests for salient terms extractor (§4.2)."""

from __future__ import annotations

from core.search.salient_terms import extract_salient_terms


def test_extracts_cve_identifiers() -> None:
    md = "# Security\n\nFixed CVE-2024-1234 and CVE-2023-56789 in kernel.\n"
    terms = extract_salient_terms(md)
    assert "CVE-2024-1234" in terms
    assert "CVE-2023-56789" in terms


def test_extracts_version_numbers() -> None:
    md = "# Kubernetes 1.29\n\nUpgrade from v1.28.3 to v1.29.0 resolves the issue.\n"
    terms = extract_salient_terms(md)
    versions = [t for t in terms if "1.2" in t or "1.28" in t or "1.29" in t]
    assert len(versions) > 0


def test_extracts_heading_tokens() -> None:
    md = "## Деплой Kubernetes\n\nSome body text.\n### Настройка Ingress\n\nMore text.\n"
    terms = extract_salient_terms(md)
    assert "Kubernetes" in terms
    assert "Ingress" in terms


def test_respects_max_terms_cap() -> None:
    # Generate many unique words
    words = [f"Term{i}" for i in range(200)]
    md = "# Heading\n\n" + " ".join(words) + "\n"
    terms = extract_salient_terms(md, max_terms=50)
    assert len(terms) <= 50


def test_stopwords_excluded() -> None:
    md = "# Заголовок\n\nЭто текст для тестирования и проверки. The quick brown fox.\n"
    terms = extract_salient_terms(md)
    stopwords = {"это", "для", "the"}
    assert not any(t.lower() in stopwords for t in terms)


def test_deduplication_preserves_first_case() -> None:
    md = "# Kubernetes\n\nkubernetes is great, Kubernetes is popular, KUBERNETES too.\n"
    terms = extract_salient_terms(md)
    # Only one entry per case-insensitive key
    lower_terms = [t.lower() for t in terms]
    assert lower_terms.count("kubernetes") == 1


def test_ghsa_identifier_extracted() -> None:
    md = "Patch for GHSA-abcd-1234-efgh released today.\n"
    terms = extract_salient_terms(md)
    assert any("GHSA" in t for t in terms)


def test_technical_acronyms_extracted() -> None:
    md = "Configure NGINX and TLS certificates for HTTPS access.\n"
    terms = extract_salient_terms(md)
    assert "NGINX" in terms or "nginx" in terms.copy()
