from scripts.audit_wider_repo_strictness import (
    collect_getattr_findings,
    collect_text_findings,
    strict_text_debt,
    unclassified_getattr_debt,
)


def test_wider_repo_getattr_defaults_are_classified() -> None:
    findings = collect_getattr_findings()
    assert unclassified_getattr_debt(findings) == []


def test_wider_repo_textual_debt_is_removed() -> None:
    findings = collect_text_findings()
    assert strict_text_debt(findings) == []
