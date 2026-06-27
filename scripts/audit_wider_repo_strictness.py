#!/usr/bin/env python3
"""Wider repository strictness audit.

The flows/runtime gate protects the agent core. This audit covers the rest of
the repo and makes dynamic access decisions explicit:

* framework/external SDK boundaries may use dynamic access in narrow adapters;
* owned typed models/services must not use ``getattr(..., default)``;
* fallback/legacy words are classified by domain instead of treated as noise.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]

PYTHON_SCAN_ROOTS: tuple[str, ...] = ("apps", "core", "scripts")
TEXT_SCAN_ROOTS: tuple[str, ...] = ("apps", "core")
SKIP_PARTS = {
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
}
SKIP_PATH_PREFIXES: tuple[str, ...] = (
    "apps/agent/desktop/vendor/",
)
SKIP_TEXT_SUFFIXES = (".map", ".min.js")
SKIP_TEXT_FILES: set[str] = set()

Decision = Literal[
    "boundary.framework",
    "boundary.external_sdk",
    "tooling",
    "strict_debt",
    "domain_strategy",
    "strict_rule_text",
]


@dataclass(frozen=True)
class AuditFinding:
    path: Path
    lineno: int
    decision: Decision
    domain: str
    message: str

    def format(self) -> str:
        rel = self.path.relative_to(REPO_ROOT).as_posix()
        return f"{rel}:{self.lineno}: {self.decision}: {self.domain}: {self.message}"


@dataclass(frozen=True)
class GetattrDecision:
    path: str
    attrs: frozenset[str]
    decision: Decision
    domain: str
    message: str


GETATTR_DECISIONS: tuple[GetattrDecision, ...] = (
    GetattrDecision(
        path="core/app_state.py",
        attrs=frozenset(
            {
                "trace_id",
                "request_id",
                "company",
                "token_data",
                "session_token_data",
                "reissue_auth_token",
            }
        ),
        decision="boundary.framework",
        domain="Starlette Request.state",
        message="middleware attaches correlation/auth fields on request.state at runtime",
    ),
)

STRICT_DEBT_TEXT_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = ()

TEXT_TERM = re.compile(r"\b(fallback|legacy|Backward-compatible)\b", re.IGNORECASE)

DOMAIN_STRATEGY_TEXT_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"fallback_models|fallback policy|fallback chain|fallback_body|LLM fallback|"
            r"BYOK fallback|fallback\.|append\(fallback\)|"
            r"fallback.*model|fallback.*provider|fallback.*pool|platform_paid_fallback|"
            r"OpenAI-compatible|custom_openai_compatible",
            re.IGNORECASE,
        ),
        "LLM provider routing and explicit fallback model policy",
    ),
    (
        re.compile(r"cbr_rate_provider|usd_to_rub_rate|CBR|Fallback-курс", re.IGNORECASE),
        "billing exchange-rate continuity policy",
    ),
    (
        re.compile(r"files/reader|docx_template|WordDocument|OLE compound|PowerPoint legacy", re.IGNORECASE),
        "document parser multi-strategy ingestion",
    ),
    (
        re.compile(r"getUserMedia|voice-recording|AudioContext|WKWebView", re.IGNORECASE),
        "browser media API compatibility strategy",
    ),
    (
        re.compile(r"offline fallback|Cache Storage|avatar|i18n|translation|label|icon", re.IGNORECASE),
        "presentation/offline UX strategy",
    ),
)

STRICT_RULE_TEXT = re.compile(
    r"No-fallback|no fallback|без .*fallback|Тихий fallback|неявн.*fallback|fallback[-а-я]*.*запрещ|запрещ.*fallback|запрещ.*legacy|Zero-fallback|Zero-Guess",
    re.IGNORECASE,
)


def _iter_files(entries: Iterable[str], suffixes: tuple[str, ...]) -> Iterable[Path]:
    for entry in entries:
        root = REPO_ROOT / entry
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in SKIP_TEXT_FILES:
                continue
            if any(rel.startswith(prefix) for prefix in SKIP_PATH_PREFIXES):
                continue
            parts = set(path.relative_to(REPO_ROOT).parts)
            if parts & SKIP_PARTS:
                continue
            if any(path.name.endswith(suffix) for suffix in SKIP_TEXT_SUFFIXES):
                continue
            yield path


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _getattr_decision(path: Path, attr: str) -> GetattrDecision | None:
    rel = path.relative_to(REPO_ROOT).as_posix()
    for decision in GETATTR_DECISIONS:
        if rel == decision.path and attr in decision.attrs:
            return decision
    return None


def collect_getattr_findings() -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for path in _iter_files(PYTHON_SCAN_ROOTS, (".py",)):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "getattr":
                continue
            if len(node.args) < 3:
                continue
            attr = _literal_string(node.args[1])
            if attr is None:
                findings.append(
                    AuditFinding(
                        path=path,
                        lineno=node.lineno,
                        decision="strict_debt",
                        domain="dynamic getattr",
                        message="getattr attribute name must be a string literal in audited code",
                    )
                )
                continue
            decision = _getattr_decision(path, attr)
            if decision is None:
                findings.append(
                    AuditFinding(
                        path=path,
                        lineno=node.lineno,
                        decision="strict_debt",
                        domain="unclassified getattr(default)",
                        message=f"unclassified getattr(..., {attr!r}, default)",
                    )
                )
                continue
            findings.append(
                AuditFinding(
                    path=path,
                    lineno=node.lineno,
                    decision=decision.decision,
                    domain=decision.domain,
                    message=decision.message,
                )
            )
    return sorted(findings, key=lambda item: (item.decision, item.path.as_posix(), item.lineno))


def _classify_text_marker(path: Path, line: str) -> tuple[Decision, str, str]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    for rule_path, pattern, message in STRICT_DEBT_TEXT_RULES:
        if rel == rule_path and pattern.search(line):
            return "strict_debt", "known wider-repo debt", message
    if (
        "core/clients/llm/" in rel
        or "core/ai/company_settings/" in rel
        or rel
        in {
            "apps/flows/src/models/node_config.py",
            "apps/flows/src/models/resource.py",
            "apps/flows/src/runtime/effective_llm_config.py",
        }
    ):
        return (
            "domain_strategy",
            "LLM provider routing and explicit fallback model policy",
            "intentional LLM fallback chain",
        )
    if rel == "apps/office/api/bff.py" and "Fallback poll" in line:
        return (
            "domain_strategy",
            "distributed lock robustness",
            "Redis pub/sub lock release has bounded poll backup",
        )
    if rel == "apps/sync/main.py" and "SPA fallback" in line:
        return (
            "domain_strategy",
            "SPA routing",
            "browser route fallback to the Sync UI shell",
        )
    if rel == "core/middleware/auth/route_config.py" and "SPA-fallback" in line:
        return (
            "domain_strategy",
            "SPA routing",
            "browser route fallback to the frontend shell",
        )
    if rel == "apps/voice/services/voice_usage.py":
        return (
            "domain_strategy",
            "billing resource lookup",
            "provider-specific price falls back to explicit category wildcard",
        )
    if rel == "core/clients/redis_client.py" and "сознательный fallback" in line:
        return (
            "domain_strategy",
            "cache read availability",
            "cache read may degrade while atomic Redis commands fail closed",
        )
    if rel == "core/clients/stt_client.py":
        return (
            "strict_rule_text",
            "strict architecture rule",
            "text states that STT client creation has no private fallback",
        )
    if STRICT_RULE_TEXT.search(line):
        return "strict_rule_text", "strict architecture rule", "text describes forbidden fallback behavior"
    haystack = f"{rel}\n{line}"
    for pattern, domain in DOMAIN_STRATEGY_TEXT_RULES:
        if pattern.search(haystack):
            return "domain_strategy", domain, "intentional domain strategy, not a hidden runtime fallback"
    if rel.endswith(".js") or "/ui/" in rel or "/frontend/" in rel:
        return "domain_strategy", "presentation fallback", "UI display fallback or legacy route marker"
    return "strict_debt", "unclassified fallback/legacy text", "requires domain owner decision"


def collect_text_findings() -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for path in _iter_files(TEXT_SCAN_ROOTS, (".py", ".js", ".ts")):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not TEXT_TERM.search(line):
                continue
            decision, domain, message = _classify_text_marker(path, line)
            findings.append(
                AuditFinding(
                    path=path,
                    lineno=lineno,
                    decision=decision,
                    domain=domain,
                    message=message,
                )
            )
    return sorted(findings, key=lambda item: (item.decision, item.path.as_posix(), item.lineno))


def unclassified_getattr_debt(findings: Iterable[AuditFinding]) -> list[AuditFinding]:
    return [finding for finding in findings if finding.decision == "strict_debt"]


def strict_text_debt(findings: Iterable[AuditFinding]) -> list[AuditFinding]:
    return [finding for finding in findings if finding.decision == "strict_debt"]


def _print_summary(getattr_findings: list[AuditFinding], text_findings: list[AuditFinding]) -> None:
    print("wider_repo_strictness_audit")
    print(f"  getattr(default) findings: {len(getattr_findings)}")
    for decision in ("boundary.framework", "boundary.external_sdk", "tooling", "strict_debt"):
        count = sum(1 for finding in getattr_findings if finding.decision == decision)
        print(f"    {decision}: {count}")
    print(f"  fallback/legacy text findings: {len(text_findings)}")
    for decision in ("strict_debt", "domain_strategy", "strict_rule_text"):
        count = sum(1 for finding in text_findings if finding.decision == decision)
        print(f"    {decision}: {count}")

    debt = [finding for finding in text_findings if finding.decision == "strict_debt"]
    if debt:
        print("  known wider-repo debt markers:")
        for finding in debt[:40]:
            print(f"    {finding.format()}")
        if len(debt) > 40:
            print(f"    ... {len(debt) - 40} more")


def main() -> int:
    getattr_findings = collect_getattr_findings()
    text_findings = collect_text_findings()
    _print_summary(getattr_findings, text_findings)

    debt = [*unclassified_getattr_debt(getattr_findings), *strict_text_debt(text_findings)]
    if debt:
        print("wider_repo_strictness_audit: FAIL", file=sys.stderr)
        for finding in debt:
            print(finding.format(), file=sys.stderr)
        return 1
    print("wider_repo_strictness_audit: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
