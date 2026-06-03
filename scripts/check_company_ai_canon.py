#!/usr/bin/env python3
"""
Канон AI provider/runtime слоя: запреты на хардкоды и обход ``core.ai``.

Запускается через ``make check-company-ai`` (см. также pre-commit).

Чеки:

1. Чтение ``company.metadata.get(...)`` для AI-ключей и ``custom_providers`` запрещено
   вне ``core/ai/company_settings/**``. Допустимо общее обращение к ``company.metadata.get`` для
   произвольных ключей пользователя; закрытые токены ниже — fail.

2. Хардкод платформенных провайдеров (``"openrouter" | "openai" | "bothub" | "yandex" |
   "provider_litserve" | "custom_openai_compatible"``) в Python вне whitelist.

3. Прямой вызов старого LLM transport entrypoint в ``apps/**`` — fail;
   требовать ``core.ai.runtime``.

4. Хардкод vendor base_url (regex) вне ``core/clients/llm/**`` и ``core/config/**``.

5. Reintroduction символов из чёрного списка (``is_llm_byok_override``,
   ``_default_rag_provider``, …).

6. Старый provider catalog entrypoint ``core.ai_provider_catalog`` и старый
   company-AI namespace запрещены.

7. Старый flows-owned model catalog запрещён: каталог моделей живёт только в
   ``core.ai.model_catalog_repository`` / shared namespace ``ai_model_catalog:*``.

8. ``core.clients.llm.factory`` запрещён как service-level public API. Вызовы
   создаются через ``core.ai.runtime``; factory остаётся только внутренним
   transport bridge и тестовой точкой покрытия.

9. Company AI settings не могут возвращать raw JSON fallback editor или
   pseudo-provider ``none``. Fallback policy редактируется только typed
   provider/model списком из backend catalog.

10. ``llm.platform_free_pool.providers`` запрещён: Humanitec LLMs free pool
    строится из canonical ``core.ai.providers``, а не из config provider-list.

11. UI/i18n не должен показывать внутреннее имя ``LitServe`` /
    ``provider_litserve`` как продуктовый provider. Публичный label — Humanitec.
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
    r"https?://(api\.openai\.com|openrouter\.ai|bothub\.chat|llm\.api\.cloud\.yandex\.net|"
    r"huggingface\.co|router\.huggingface\.co|api\.groq\.com|generativelanguage\.googleapis\.com|"
    r"models\.github\.ai|api\.deepinfra\.com)"
)


_PROVIDER_LITERALS_RE = re.compile(
    r"['\"](openrouter|openai|bothub|yandex|provider_litserve|custom_openai_compatible)['\"]"
)


_OLD_LLM_TRANSPORT_CALL_RE = re.compile(r"\bget_" + r"llm\s*\(")
_DIRECT_LLM_FACTORY_IMPORT_RE = re.compile(
    r"^\s*(from\s+core\.clients\.llm\.factory\s+import|"
    r"import\s+core\.clients\.llm\.factory\b)",
    re.MULTILINE,
)
_DIRECT_LLM_TRANSPORT_RUNTIME_IMPORT_RE = re.compile(
    r"^\s*(from\s+core\.clients\.llm\.runtime\s+import\b[^\n]*"
    r"create_llm_transport_client|import\s+core\.clients\.llm\.runtime\b)",
    re.MULTILINE,
)
_OLD_LLM_FREE_POOL_IMPORT_RE = re.compile(
    r"^\s*(from\s+core\.clients\.llm\.platform_free_models\s+import|"
    r"import\s+core\.clients\.llm\.platform_free_models\b)",
    re.MULTILINE,
)
_OLD_FREE_POOL_DISCOVERY_RE = re.compile(
    r"\b(OpenRouterPlatformFreeModelAdapter|BotHubFreeModelAdapter|"
    r"ConfiguredAccountFreeTierModelAdapter|platform_free_model_adapters_for_settings|"
    r"is_openrouter_verified_free_text_model|is_bothub_free_text_model)\b"
)
_OLD_FREE_POOL_PROVIDERS_CONFIG_RE = re.compile(r"\bplatform_free_pool\.providers\b")
_OLD_FREE_POOL_PROVIDERS_JSON_RE = re.compile(
    r'"platform_free_pool"\s*:\s*\{[\s\S]{0,1600}"providers"\s*:'
)
_DIRECT_LLM_PACKAGE_GET_LLM_IMPORT_RE = re.compile(
    r"^\s*from\s+core\.clients\.llm\s+import\b[^\n]*\b("
    r"get_" + r"llm|get_" + r"llm_for_state)\b",
    re.MULTILINE,
)
_OLD_AI_PROVIDER_CATALOG_RE = re.compile(r"\bcore\.ai_provider_catalog\b")
_OLD_COMPANY_AI_NAMESPACE_RE = re.compile(
    r"^\s*(from\s+core\.company_ai\b|import\s+core\.company_ai\b)",
    re.MULTILINE,
)
_OLD_COMPANY_AI_RESOLUTION_RE = re.compile(r"\bcore\.ai\.company_resolution\b")
_COMPANY_SETTINGS_RUNTIME_EXPORT_RE = re.compile(
    r"^\s*from\s+core\.ai\.company_settings\s+import\b[^\n]*"
    r"(resolve_llm_for_capability|resolve_embedding_for_company|resolve_rerank_for_company|"
    r"resolve_voice_for_company|resolve_custom_llm_provider_ref|ResolvedLLM|ResolvedEmbedding|"
    r"ResolvedRerank|ResolvedVoice)",
    re.MULTILINE,
)
_DIRECT_CORE_AI_CONCRETE_RESOLVER_RE = re.compile(
    r"^\s*from\s+core\.ai\.resolver\s+import\b[^\n]*(resolve_llm_for_capability|"
    r"resolve_embedding_for_company|resolve_rerank_for_company|resolve_voice_for_company|"
    r"resolve_custom_llm_provider_ref|ResolvedLLM|ResolvedEmbedding|ResolvedRerank|ResolvedVoice)",
    re.MULTILINE,
)
_OLD_RAG_EMBEDDING_SERVICE_IMPORT_RE = re.compile(
    r"^\s*(from\s+core\.rag\.services\.embedding_service\s+import|"
    r"import\s+core\.rag\.services\.embedding_service\b)",
    re.MULTILINE,
)
_OLD_FLOWS_LLM_MODEL_REPOSITORY_RE = re.compile(
    r"\b(apps\.flows\.src\.db\.llm_model_repository|LLMModelRepository|"
    r"flows_llm_model_repository)\b"
)
_OLD_FLOWS_LLM_MODEL_RECORD_RE = re.compile(
    r"^\s*(from\s+apps\.flows\.src\.models\.llm_model\s+import|"
    r"import\s+apps\.flows\.src\.models\.llm_model\b)",
    re.MULTILINE,
)
_OLD_LLM_MODEL_STORAGE_PREFIX_RE = re.compile(r"['\"]llm_model:")
_OLD_EMBEDDING_SERVICE_NAME_RE = re.compile(r"\bEmbeddingService\b")
_DIRECT_EMBEDDING_TRANSPORT_CONSTRUCTOR_RE = re.compile(r"\bAIEmbeddingClient\s*\(")
_DIRECT_RERANK_TRANSPORT_CONSTRUCTOR_RE = re.compile(r"\bAIRerankerHTTPClient\s*\(")
_APP_MODEL_CATALOG_DISCOVERY_RE = re.compile(
    r"\b(request_with_strategy|httpx|resolve_provider_openai_v1_base_url|"
    r"LLM_PROVIDER_DEFAULT_MODELS_URLS|GITHUB_MODELS_API_VERSION|"
    r"yandex_provider_http_headers|models_url|_fetch_provider_catalog_payload)\b"
    r"|https?://"
)
_RAW_FALLBACK_UI_RE = re.compile(
    r"(fallback_models[\s\S]{0,800}type=\"object\"|"
    r"type=\"object\"[\s\S]{0,800}fallback_models|"
    r"fallback_models expects JSON array|"
    r"Fallback policy \(JSON array\)|"
    r"fallback_models_label[^\n]+JSON array)"
)
_PSEUDO_NONE_PROVIDER_UI_RE = re.compile(r"\b(_NONE_PROVIDER|_isNoneProvider)\b")
_FORBIDDEN_HUMANITEC_MODELS_UI_LEAK_RE = re.compile(
    r"LitServe|Silero \(litserve\)|provider_litserve\.infra|"
    r"provider_litserve/(models|model_retry)|frontend/dashboard_litserve_models_count|"
    r"\b(LitserveModelsPage|LitserveApp|LitserveSidebar|dashboardLitserveModelsCountOp)\b|"
    r"Неизвестная litserve|Local LitServe|Реестр моделей LitServe|LitServe model registry"
)


METADATA_KEY_RE = re.compile(
    r"company\.metadata\.get\(\s*['\"]("
    + "|".join(re.escape(k) for k in _FORBIDDEN_METADATA_KEYS)
    + r")['\"]"
)


PROVIDER_WHITELIST_PATHS = (
    "core/ai/",
    "core/clients/llm/",
    "core/ai/adapters/",
    "core/clients/voice_resolver.py",
    "core/clients/voice_resolver/",
    "core/clients/stt_client.py",
    "core/clients/tts_client.py",
    "core/clients/speech_override.py",
    "core/clients/speech_provider_catalog.py",
    "core/clients/tts_pronunciation/",
    "core/app/server.py",
    "core/config/",
    "core/ai/company_settings/",
    "core/billing/default_settlement_rules.py",
    "core/db/models/platform.py",
    "core/integrations/models.py",
    "core/middleware/dev_inter_service_proxy.py",
    "core/models/calendar_models.py",
    "core/models/identity_models.py",
    "core/models/voice_providers_catalog.py",
    "core/types.py",
    "core/rag/embedding_runtime.py",
    "core/rag/post_retrieval_rerank.py",
    "core/rag/providers/agentset_provider.py",
    "core/rag/providers/pgvector_provider.py",
    "core/text_transforms/",
    "apps/flows/bundles/",
    "apps/flows/src/runtime/llm_byok.py",
    "apps/flows/src/runtime/nodes.py",
    "apps/flows/src/runtime/runners/llm_runner.py",
    "apps/flows/src/resources/wrappers/llm_resource.py",
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


OLD_LLM_TRANSPORT_WHITELIST_PATHS = (
    "core/ai/",
    "core/clients/llm/",
    "scripts/",
)


AI_TRANSPORT_CONSTRUCTOR_WHITELIST_PATHS = (
    "core/ai/",
    "core/ai/runtime.py",
    "tests/core/ai/",
)


VENDOR_URL_WHITELIST_PATHS = (
    "core/ai/adapters/",
    "core/ai/providers/",
    "core/ai/embedding_client.py",
    "core/clients/llm/",
    "core/clients/voice_resolver.py",
    "core/clients/stt_client.py",
    "core/clients/tts_client.py",
    "core/config/",
    "core/files/reader/",
    "scripts/",
    "tests/",
    "conf.json",
    "docs/",
    ".cursor/",
)


METADATA_WHITELIST_PATHS = (
    "core/ai/",
    "core/ai/company_settings/",
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


def _company_ai_ui_files() -> tuple[Path, ...]:
    return (
        REPO_ROOT / "core/frontend/static/lib/components/llm/llm-config-editor.js",
        REPO_ROOT / "apps/frontend/ui/pages/settings/settings-page.js",
        REPO_ROOT / "core/i18n/translations/en/frontend.json",
        REPO_ROOT / "core/i18n/translations/ru/frontend.json",
        REPO_ROOT / "core/i18n/generated/en.json",
        REPO_ROOT / "core/i18n/generated/ru.json",
    )


def _humanitec_models_ui_surface_files() -> list[Path]:
    roots = (
        REPO_ROOT / "apps/frontend/ui",
        REPO_ROOT / "apps/provider_litserve/ui",
        REPO_ROOT / "core/frontend/static/lib",
        REPO_ROOT / "core/i18n/translations",
        REPO_ROOT / "core/i18n/generated",
    )
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix in {".js", ".json", ".html"}:
                out.append(path)
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

        # 1. legacy-ключи metadata
        if not _path_starts_with_any(rel, METADATA_WHITELIST_PATHS):
            for m in METADATA_KEY_RE.finditer(text):
                failures.append(f"{rel}: forbidden company.metadata.get({m.group(1)!r}) outside core.ai.company_settings")

        # 2. provider literals
        if not _path_starts_with_any(rel, PROVIDER_WHITELIST_PATHS):
            for m in _PROVIDER_LITERALS_RE.finditer(text):
                failures.append(f"{rel}: hardcoded provider literal {m.group(1)!r} outside whitelist")

        # 3. old LLM transport factory calls outside whitelist
        if not _path_starts_with_any(rel, OLD_LLM_TRANSPORT_WHITELIST_PATHS):
            for _ in _OLD_LLM_TRANSPORT_CALL_RE.finditer(text):
                failures.append(
                    f"{rel}: direct old LLM transport factory call outside whitelist; "
                    "use core.ai.runtime instead"
                )

        if not (
            rel.startswith("core/ai/")
            or rel.startswith("core/clients/llm/")
            or rel.startswith("tests/")
            or rel == "scripts/check_company_ai_canon.py"
        ):
            if _DIRECT_LLM_FACTORY_IMPORT_RE.search(text):
                failures.append(
                    f"{rel}: core.clients.llm.factory import is forbidden; "
                    "use core.ai.runtime"
                )
            if _DIRECT_LLM_TRANSPORT_RUNTIME_IMPORT_RE.search(text):
                failures.append(
                    f"{rel}: core.clients.llm.runtime transport import is forbidden; "
                    "use core.ai.runtime"
                )
            if _OLD_LLM_FREE_POOL_IMPORT_RE.search(text):
                failures.append(
                    f"{rel}: core.clients.llm platform free-pool import is forbidden; "
                    "use core.ai.free_pool"
                )
            if _DIRECT_LLM_PACKAGE_GET_LLM_IMPORT_RE.search(text):
                failures.append(
                    f"{rel}: old LLM transport factory import from core.clients.llm is forbidden; "
                    "use core.ai.runtime"
                )

        # 4. vendor base_url outside whitelist
        if not _path_starts_with_any(rel, VENDOR_URL_WHITELIST_PATHS):
            for m in _VENDOR_URL_RE.finditer(text):
                failures.append(f"{rel}: hardcoded vendor URL {m.group(0)!r} outside whitelist")

        # 5. запрещённые legacy-символы (повторное введение)
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

        if _OLD_AI_PROVIDER_CATALOG_RE.search(text) and rel != "scripts/check_company_ai_canon.py":
            failures.append(f"{rel}: forbidden old core.ai_provider_catalog import path")

        if _OLD_COMPANY_AI_NAMESPACE_RE.search(text):
            failures.append(
                f"{rel}: old company-AI namespace import is forbidden; "
                "use core.ai.company_settings"
            )
        if _OLD_COMPANY_AI_RESOLUTION_RE.search(text) and rel != "scripts/check_company_ai_canon.py":
            failures.append(
                f"{rel}: core.ai.company_resolution is forbidden; "
                "use core.ai.company_settings.resolver internally or core.ai.resolver publicly"
            )
        if _OLD_FREE_POOL_DISCOVERY_RE.search(text) and rel != "scripts/check_company_ai_canon.py":
            failures.append(
                f"{rel}: free-pool provider-specific discovery is forbidden; "
                "build Humanitec LLMs free pool from core.ai.model_catalog_repository"
            )
        if _OLD_FREE_POOL_PROVIDERS_CONFIG_RE.search(text) and rel != "scripts/check_company_ai_canon.py":
            failures.append(
                f"{rel}: llm.platform_free_pool.providers is forbidden; "
                "free-pool providers come from core.ai.providers"
            )

        if _COMPANY_SETTINGS_RUNTIME_EXPORT_RE.search(text) and not (
            rel.startswith("core/ai/company_settings/")
            or rel.startswith("tests/core/ai/company_settings/")
            or rel == "scripts/check_company_ai_canon.py"
        ):
            failures.append(
                f"{rel}: runtime resolver import from core.ai.company_settings is forbidden; "
                "use core.ai.resolver/core.ai.runtime"
            )

        if _DIRECT_CORE_AI_CONCRETE_RESOLVER_RE.search(text) and rel != "core/ai/resolver.py":
            failures.append(
                f"{rel}: concrete resolver import from core.ai.resolver is forbidden; "
                "use resolve_ai_model/core.ai.runtime"
            )

        if _OLD_RAG_EMBEDDING_SERVICE_IMPORT_RE.search(text):
            failures.append(
                f"{rel}: core.rag.services.embedding_service import is forbidden; "
                "use core.ai.embedding_client/core.ai.runtime"
            )
        if _OLD_EMBEDDING_SERVICE_NAME_RE.search(text) and rel != "scripts/check_company_ai_canon.py":
            failures.append(
                f"{rel}: old EmbeddingService symbol is forbidden; "
                "use core.ai.embedding_client.AIEmbeddingClient"
            )

        if rel != "scripts/check_company_ai_canon.py":
            if _OLD_FLOWS_LLM_MODEL_REPOSITORY_RE.search(text):
                failures.append(
                    f"{rel}: flows-owned LLM model catalog repository is forbidden; "
                    "use core.ai.model_catalog_repository"
                )
            if _OLD_FLOWS_LLM_MODEL_RECORD_RE.search(text):
                failures.append(
                    f"{rel}: flows-owned LLMModel record is forbidden; "
                    "use core.ai.models.AIModelRecord"
                )
            if _OLD_LLM_MODEL_STORAGE_PREFIX_RE.search(text):
                failures.append(
                    f"{rel}: old llm_model:* storage namespace is forbidden; "
                    "use ai_model_catalog:*"
                )

        if not _path_starts_with_any(rel, AI_TRANSPORT_CONSTRUCTOR_WHITELIST_PATHS):
            if _DIRECT_EMBEDDING_TRANSPORT_CONSTRUCTOR_RE.search(text):
                failures.append(
                    f"{rel}: direct AIEmbeddingClient construction is forbidden; "
                    "use core.ai.runtime"
                )
            if _DIRECT_RERANK_TRANSPORT_CONSTRUCTOR_RE.search(text):
                failures.append(
                    f"{rel}: direct AIRerankerHTTPClient construction is forbidden; "
                    "use core.ai.runtime.rerank_scores"
                )

        if rel == "apps/flows/src/services/llm_models_service.py" and _APP_MODEL_CATALOG_DISCOVERY_RE.search(text):
            failures.append(
                f"{rel}: provider catalog HTTP/discovery code is forbidden in flows; "
                "use core.ai.adapters"
            )

    for config_name in ("conf.json", "conf.local.json"):
        config_path = REPO_ROOT / config_name
        if not config_path.exists():
            continue
        try:
            text = config_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if _OLD_FREE_POOL_PROVIDERS_JSON_RE.search(text):
            failures.append(
                f"{config_name}: llm.platform_free_pool.providers is forbidden; "
                "free-pool providers come from core.ai.providers"
            )

    for path in _company_ai_ui_files():
        if not path.exists():
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if _RAW_FALLBACK_UI_RE.search(text):
            failures.append(
                f"{rel}: raw JSON fallback editor/text is forbidden; "
                "use typed provider/model fallback editor"
            )
        if _PSEUDO_NONE_PROVIDER_UI_RE.search(text):
            failures.append(
                f"{rel}: pseudo-provider none in company AI settings is forbidden; "
                "use typed enabled/provider/model contracts"
            )

    for path in _humanitec_models_ui_surface_files():
        if not path.exists():
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        match = _FORBIDDEN_HUMANITEC_MODELS_UI_LEAK_RE.search(text)
        if match:
            failures.append(
                f"{rel}: forbidden Humanitec Models UI label leak {match.group(0)!r}; "
                "use Humanitec/Humanitec Models public naming"
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
