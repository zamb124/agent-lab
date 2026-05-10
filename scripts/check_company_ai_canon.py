#!/usr/bin/env python3
"""
Канон company AI providers: запреты на хардкоды и reintroduction удалённых символов.

Запускается через ``make check-company-ai`` (см. также pre-commit).

Чеки:

1. Чтение ``company.metadata.get(...)`` для AI-ключей и ``custom_providers`` запрещено
   вне ``core/company_ai/**``. Допустимо общее обращение к ``company.metadata.get`` для
   произвольных ключей пользователя; закрытые токены ниже — fail.

2. Хардкод платформенных провайдеров (``"openrouter" | "openai" | "bothub" | "yandex" |
   "provider_litserve" | "custom_openai_compatible"``) в Python вне whitelist.

3. Прямой вызов ``get_llm(`` в ``apps/**`` (кроме whitelist) — fail; требовать
   ``resolve_llm_for_capability(...)``.

4. Хардкод vendor base_url (regex) вне ``core/clients/llm/**`` и ``core/config/**``.

5. Reintroduction символов из чёрного списка (``is_llm_byok_override``,
   ``_default_rag_provider``, …).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


_FORBIDDEN_LEGACY_SYMBOLS: tuple[str, ...] = (
    "_default_rag_provider",
    "reset_default_rag_provider_cache",
    "get_default_rag_provider",
    "_build_crm_pgvector_provider",
    "CRM_SUMMARIZE_PROVIDER_KEY",
    "RAG_EMBEDDING_OVERRIDE_KEY",
    "RAG_RERANK_OVERRIDE_KEY",
    "CompanyUiAiConfig",
    "company_ui_ai",
    "CRM_SUMMARIZE_LLM_METADATA_KEY",
    "VoiceUsageTracker",
    "SANDBOX_CODEGEN_DEFAULT_MODEL",
    "parse_rag_embedding_override_provider",
    "parse_rag_rerank_override",
    "parse_crm_summarize_provider",
    "resolve_crm_summarize_llm_pair",
)


_FORBIDDEN_METADATA_KEYS: tuple[str, ...] = (
    "rag_embedding_override",
    "rag_rerank_override",
    "crm_summarize_provider",
    "ai_providers",
)


_VENDOR_URL_RE = re.compile(
    r"https?://(api\.openai\.com|openrouter\.ai|bothub\.chat|llm\.api\.cloud\.yandex\.net|huggingface\.co)"
)


_PROVIDER_LITERALS_RE = re.compile(
    r"['\"](openrouter|openai|bothub|yandex|provider_litserve|custom_openai_compatible)['\"]"
)


_GET_LLM_CALL_RE = re.compile(r"\bget_llm\s*\(")


METADATA_KEY_RE = re.compile(
    r"company\.metadata\.get\(\s*['\"]("
    + "|".join(re.escape(k) for k in _FORBIDDEN_METADATA_KEYS)
    + r")['\"]"
)


PROVIDER_WHITELIST_PATHS = (
    "core/clients/llm/",
    "core/clients/voice_resolver.py",
    "core/clients/voice_resolver/",
    "core/clients/stt_client.py",
    "core/clients/tts_client.py",
    "core/clients/speech_override.py",
    "core/clients/speech_provider_catalog.py",
    "core/clients/tts_pronunciation/",
    "core/config/",
    "core/company_ai/",
    "core/billing/default_settlement_rules.py",
    "core/db/models/platform.py",
    "core/integrations/models.py",
    "core/middleware/dev_inter_service_proxy.py",
    "core/models/calendar_models.py",
    "core/models/identity_models.py",
    "core/models/voice_providers_catalog.py",
    "core/rag/embedding_runtime.py",
    "core/rag/post_retrieval_rerank.py",
    "core/rag/providers/agentset_provider.py",
    "core/rag/providers/pgvector_provider.py",
    "core/rag/services/embedding_service.py",
    "core/text_transforms/",
    "apps/flows/bundles/",
    "apps/flows/src/runtime/llm_byok.py",
    "apps/flows/src/runtime/nodes.py",
    "apps/flows/src/runtime/runners/llm_runner.py",
    "apps/flows/src/resources/wrappers/llm_resource.py",
    "apps/flows/src/services/llm_models_service.py",
    "apps/flows/src/models/node_config.py",
    "apps/flows/src/models/resource.py",
    "apps/flows/tools/sandbox_codegen.py",
    "apps/frontend/api/ai_providers.py",
    "apps/frontend/api/services.py",
    "apps/frontend/api/company_voice_providers.py",
    "apps/frontend/api/voice_providers_catalog_helpers.py",
    "apps/frontend/models.py",
    "apps/crm_worker/tasks/note_markdown_tasks.py",
    "apps/provider_litserve/",
    "migrations/",
    "scripts/",
    "tests/",
    "conf.json",
)


GET_LLM_WHITELIST_PATHS = (
    "core/",
    "apps/flows/",
    "apps/flows_worker/",
    "apps/idle_worker/",
    "scripts/",
    "tests/",
)


VENDOR_URL_WHITELIST_PATHS = (
    "core/clients/llm/",
    "core/clients/voice_resolver.py",
    "core/clients/stt_client.py",
    "core/clients/tts_client.py",
    "core/config/",
    "core/files/reader/",
    "core/rag/services/embedding_service.py",
    "apps/flows/src/services/llm_models_service.py",
    "scripts/",
    "tests/",
    "conf.json",
    "docs/",
    ".cursor/",
)


METADATA_WHITELIST_PATHS = (
    "core/company_ai/",
    "scripts/",
    "tests/",
    "docs/",
    ".cursor/",
)


def _iter_python_files() -> list[Path]:
    out: list[Path] = []
    for p in REPO_ROOT.rglob("*.py"):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if any(
            rel.startswith(prefix)
            for prefix in (".venv/", "node_modules/", "build/", ".git/", "coverage/", "dist/")
        ):
            continue
        out.append(p)
    return out


def _path_starts_with_any(rel: str, prefixes: tuple[str, ...]) -> bool:
    return any(rel.startswith(p) for p in prefixes)


def main() -> int:
    failures: list[str] = []
    for path in _iter_python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        # 1. metadata legacy keys
        if not _path_starts_with_any(rel, METADATA_WHITELIST_PATHS):
            for m in METADATA_KEY_RE.finditer(text):
                failures.append(f"{rel}: forbidden company.metadata.get({m.group(1)!r}) outside core.company_ai")

        # 2. provider literals
        if not _path_starts_with_any(rel, PROVIDER_WHITELIST_PATHS):
            for m in _PROVIDER_LITERALS_RE.finditer(text):
                failures.append(f"{rel}: hardcoded provider literal {m.group(1)!r} outside whitelist")

        # 3. get_llm calls outside whitelist
        if not _path_starts_with_any(rel, GET_LLM_WHITELIST_PATHS):
            for _ in _GET_LLM_CALL_RE.finditer(text):
                failures.append(
                    f"{rel}: direct get_llm( call outside whitelist; "
                    "use core.company_ai.resolve_llm_for_capability instead"
                )

        # 4. vendor base_url outside whitelist
        if not _path_starts_with_any(rel, VENDOR_URL_WHITELIST_PATHS):
            for m in _VENDOR_URL_RE.finditer(text):
                failures.append(f"{rel}: hardcoded vendor URL {m.group(0)!r} outside whitelist")

        # 5. forbidden legacy symbols (reintroduction)
        for sym in _FORBIDDEN_LEGACY_SYMBOLS:
            # допускаем упоминание в комментариях/docstring внутри scripts/check_company_ai_canon.py
            # и в .cursor/* / scripts/* / docs/*
            if rel == "scripts/check_company_ai_canon.py":
                continue
            if rel.startswith("docs/") or rel.startswith(".cursor/") or rel.startswith("scripts/"):
                continue
            if sym in text:
                # допускаем упоминание в строке — fail только при импорте/определении
                pat_def = re.compile(r"\b(def|class)\s+" + re.escape(sym) + r"\b")
                pat_import = re.compile(r"\bfrom\s+\S+\s+import\b[^\n]*\b" + re.escape(sym) + r"\b")
                pat_assign = re.compile(r"^\s*" + re.escape(sym) + r"\s*[:=]", re.MULTILINE)
                if pat_def.search(text) or pat_import.search(text) or pat_assign.search(text):
                    failures.append(
                        f"{rel}: forbidden reintroduction of legacy symbol {sym!r}"
                    )

    if failures:
        print("FAIL: company AI canon violations:")
        for line in failures:
            print(f"  {line}")
        return 1
    print("OK: company AI canon")
    return 0


if __name__ == "__main__":
    sys.exit(main())
