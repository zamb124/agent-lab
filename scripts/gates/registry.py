"""Реестр гейтов: имя, команда, сьюты прогона."""

from __future__ import annotations

from dataclasses import dataclass

SUITES = frozenset({"lint", "lint_ts", "static", "network", "events"})


def _py(module: str, *args: str) -> tuple[str, ...]:
    return ("python", "-m", module, *args)


def _sh(path: str) -> tuple[str, ...]:
    return ("bash", path)


@dataclass(frozen=True)
class Gate:
    name: str
    argv: tuple[str, ...]
    suites: frozenset[str]

    def __post_init__(self) -> None:
        unknown = self.suites - SUITES
        if unknown:
            raise RuntimeError(f"{self.name}: unknown suites {sorted(unknown)}")


_LINT = frozenset({"lint"})
_TS = frozenset({"lint_ts"})
_LINT_EVENTS = frozenset({"lint", "events"})
_TS_EVENTS = frozenset({"lint_ts", "events"})
_STATIC = frozenset({"static"})
_NETWORK = frozenset({"network"})

GATES: tuple[Gate, ...] = (
    Gate("backend.strict_agent_architecture", _py("scripts.gates.backend.strict_agent_architecture"), _LINT),
    Gate("backend.wider_repo_strictness", _py("scripts.gates.backend.wider_repo_strictness"), _LINT),
    Gate("backend.cross_service_imports", _py("scripts.gates.backend.cross_service_imports"), _LINT),
    Gate("backend.command_owner_catalogs", _py("scripts.gates.backend.command_owner_catalogs"), _LINT),
    Gate("backend.rest_handlers_call_ops", _py("scripts.gates.backend.rest_handlers_call_ops"), _LINT),
    Gate("backend.dependency_injection", _py("scripts.gates.backend.dependency_injection"), _LINT),
    Gate("backend.forbidden_paths", _py("scripts.gates.backend.forbidden_paths"), _LINT),
    Gate("backend.ratchet_counts", _py("scripts.gates.backend.ratchet_counts"), _LINT),
    Gate("backend.model_files", _py("scripts.gates.backend.model_files"), _LINT),
    Gate("backend.model_method_order_names", _py("scripts.gates.backend.model_method_order_names"), _LINT),
    Gate("backend.migration_files", _py("scripts.gates.backend.migration_files"), _LINT),
    Gate("backend.stock_service_queries", _py("scripts.gates.backend.stock_service_queries"), _LINT),
    Gate("backend.redis_ttl", _py("scripts.gates.backend.redis_ttl"), _LINT),
    Gate("backend.taskiq", _py("scripts.gates.backend.taskiq"), _LINT),
    Gate("backend.billing_span", _py("scripts.gates.backend.billing_span"), _LINT),
    Gate("backend.backend_error_i18n", _py("scripts.gates.backend.backend_error_i18n"), _LINT),
    Gate("backend.command_rest_mirror", _py("scripts.gates.backend.command_rest_mirror"), _TS_EVENTS),
    Gate("backend.platform_events", _py("scripts.gates.backend.platform_events"), _TS_EVENTS),
    Gate("backend.realtime", _py("scripts.gates.backend.realtime"), _TS_EVENTS),
    Gate("backend.logging", _sh("scripts/gates/backend/logging_canon.sh"), _TS),
    Gate("backend.no_uvicorn", _sh("scripts/gates/backend/no_uvicorn.sh"), _TS_EVENTS),
    Gate("authz.canon", _py("scripts.gates.authz.canon"), _LINT),
    Gate("authz.dual_write", _py("scripts.gates.authz.dual_write"), _LINT),
    Gate("authz.backfill_completeness", _py("scripts.gates.authz.backfill_completeness"), _LINT),
    Gate("authz.model", _py("scripts.gates.authz.model"), _LINT),
    Gate("files.files_canon", _py("scripts.gates.files.files_canon"), _LINT_EVENTS),
    Gate("files.object_store", _py("scripts.gates.files.object_store"), _LINT_EVENTS),
    Gate("files.file_reader", _py("scripts.gates.files.file_reader"), _TS_EVENTS),
    Gate("files.office_file_id", _py("scripts.gates.files.office_file_id"), _LINT),
    Gate("files.corpus_manifest", _py("scripts.gates.files.corpus_manifest"), _TS_EVENTS),
    Gate("files.files_ui", _sh("scripts/gates/files/files_ui_canon.sh"), _LINT_EVENTS),
    Gate("voice.resolver_usage", _py("scripts.gates.voice.resolver_usage"), _TS_EVENTS),
    Gate("voice.speakable_parity", _py("scripts.gates.voice.speakable_parity"), _TS_EVENTS),
    Gate("voice.tts_pipeline_single_apply", _py("scripts.gates.voice.tts_pipeline_single_apply"), _TS_EVENTS),
    Gate("ai.company_ai_canon", _py("scripts.gates.ai.company_ai_canon"), _TS_EVENTS),
    Gate("ai.rag_post_retrieval_rerank_single", _py("scripts.gates.ai.rag_post_retrieval_rerank_single"), _TS_EVENTS),
    Gate("flows.tool_tags", _py("scripts.gates.flows.tool_tags"), _LINT),
    Gate("flows.tool_contracts", _py("scripts.gates.flows.tool_contracts"), _LINT),
    Gate("flows.mcp_branding_bundle", _py("scripts.gates.flows.mcp_branding_bundle"), _LINT_EVENTS),
    Gate("flows.flow_ui_hard_cut", _py("scripts.gates.flows.flow_ui_hard_cut"), _TS_EVENTS),
    Gate("sync.op_adapters", _py("scripts.gates.sync.op_adapters"), _LINT),
    Gate("frontend.ui_canon", _sh("scripts/gates/frontend/ui_canon.sh"), _TS_EVENTS),
    Gate("frontend.field_canon", _sh("scripts/gates/frontend/field_canon.sh"), _TS),
    Gate("frontend.ui_factories", _py("scripts.gates.frontend.ui_factories"), _TS_EVENTS),
    Gate("frontend.ui_kit_canon", _py("scripts.gates.frontend.ui_kit_canon"), _TS),
    Gate("frontend.ui_kit_docs", _py("scripts.gates.frontend.ui_kit_docs"), _TS),
    Gate("frontend.core_frontend_canon", _py("scripts.gates.frontend.core_frontend_canon"), _TS_EVENTS),
    Gate("frontend.embed_esm_closure", _py("scripts.gates.frontend.embed_esm_closure"), _TS_EVENTS),
    Gate("frontend.css_template_balance", _py("scripts.gates.frontend.css_template_balance"), _TS),
    Gate("frontend.platform_typography", _py("scripts.gates.frontend.platform_typography"), frozenset()),
    Gate("frontend.i18n", _sh("scripts/gates/frontend/i18n.sh"), _TS_EVENTS),
    Gate(
        "frontend.i18n_keys",
        _py("scripts.gates.frontend.i18n_keys", "--mode", "missing", "--strict"),
        _TS_EVENTS,
    ),
    Gate("repo.repo_hygiene", _py("scripts.gates.repo.repo_hygiene"), _LINT),
    Gate("repo.rules_drift", _py("scripts.gates.repo.rules_drift"), _LINT),
    Gate("repo.conf_secrets", _py("scripts.gates.repo.conf_secrets"), _LINT),
    Gate("repo.conf_keys_declared", _py("scripts.gates.repo.conf_keys_declared"), _LINT),
    Gate("repo.platform_brand_hardcode", _py("scripts.gates.repo.platform_brand_hardcode"), _LINT),
    Gate("repo.variables_legacy", _sh("scripts/gates/repo/variables_legacy.sh"), _LINT),
    Gate("repo.ft_wheels", _sh("scripts/gates/repo/ft_wheels.sh"), _NETWORK),
    Gate("repo.gpu_dockerfile", _sh("scripts/gates/repo/gpu_dockerfile_llm_model.sh"), frozenset()),
    Gate("repo.docs_locale_parity", _py("scripts.gates.repo.docs_locale_parity"), frozenset()),
    Gate(
        "repo.scenario_docs_quality",
        _py("scripts.gates.repo.scenario_docs_quality", "--warnings-ok"),
        frozenset(),
    ),
    Gate("repo.scripts_layout", _py("scripts.gates.repo.scripts_layout"), _LINT),
    Gate("repo.public_pages_canon", _py("scripts.gates.repo.public_pages_canon"), _LINT),
    Gate("generate.a2a_fixtures", _py("scripts.generate.a2a_fixtures", "--check"), _STATIC),
    Gate("generate.a2a_fixtures_remote", _py("scripts.generate.a2a_fixtures", "--check-remote"), _NETWORK),
)

_BY_NAME = {gate.name: gate for gate in GATES}
if len(_BY_NAME) != len(GATES):
    raise RuntimeError("duplicate gate name")


def by_name(name: str) -> Gate:
    try:
        return _BY_NAME[name]
    except KeyError as exc:
        known = ", ".join(sorted(_BY_NAME))
        raise SystemExit(f"unknown gate {name}. known: {known}") from exc


def select_suite(suite: str) -> tuple[Gate, ...]:
    if suite not in SUITES:
        raise SystemExit(f"unknown suite {suite}. known: {', '.join(sorted(SUITES))}")
    return tuple(gate for gate in GATES if suite in gate.suites)
