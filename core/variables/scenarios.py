"""Каталог платформенных сценариев работы с переменными.

Используется как опора для demo-seed (`demo_company_variables.json`), example bundles
и E2E-тестов: каждый сценарий имеет стабильный id и демо-ключ переменной.
"""

from __future__ import annotations

from enum import StrEnum


class VariableScenario(StrEnum):
    COMPANY_STATIC = "company_static"
    COMPANY_SECRET_ENCRYPTED = "company_secret_encrypted"
    SECRET_SHARED_FOR_EXECUTION = "secret_shared_for_execution"
    SECRET_PRIVATE_OWNER = "secret_private_owner"
    SCOPED_BY_NAMESPACE = "scoped_by_namespace"
    SCOPED_BY_USER_ID = "scoped_by_user_id"
    SCOPED_BY_CHANNEL = "scoped_by_channel"
    SCOPED_BY_VAR = "scoped_by_var"
    EXPRESSION_WITH_VAR_REFS = "expression_with_var_refs"
    VAR_DEPENDENCY_TOPOSORT = "var_dependency_toposort"
    FLOW_STATIC_LITERAL = "flow_static_literal"
    FLOW_VAR_REFERENCE = "flow_var_reference"
    BRANCH_VARIABLES_MERGE = "branch_variables_merge"
    BRANCH_VARIABLES_REPLACE = "branch_variables_replace"
    RUNTIME_METADATA_OVERRIDE = "runtime_metadata_override"
    IDENTITY_VARIABLES = "identity_variables"
    PROMPT_TEMPLATE_RENDER = "prompt_template_render"
    MCP_HEADER_VAR_REF = "mcp_header_var_ref"
    PUBLIC_AGENT_CARD = "public_agent_card"
    LEDGER_VARIABLES_RESOLVED = "ledger_variables_resolved"
    VERSIONING = "versioning"


VARIABLE_SCENARIO_DESCRIPTIONS: dict[VariableScenario, str] = {
    VariableScenario.COMPANY_STATIC: "Несекретная company-переменная в secrets-сервисе",
    VariableScenario.COMPANY_SECRET_ENCRYPTED: "Секрет шифруется at rest, маскируется в API",
    VariableScenario.SECRET_SHARED_FOR_EXECUTION: "Секрет доступен любому исполнителю flow компании",
    VariableScenario.SECRET_PRIVATE_OWNER: "Секрет только для created_by исполнителя",
    VariableScenario.SCOPED_BY_NAMESPACE: "Scoped override по namespace контекста",
    VariableScenario.SCOPED_BY_USER_ID: "Scoped override по user_id исполнителя",
    VariableScenario.SCOPED_BY_CHANNEL: "Scoped override по channel контекста",
    VariableScenario.SCOPED_BY_VAR: "Scoped override по значению другой переменной",
    VariableScenario.EXPRESSION_WITH_VAR_REFS: "value_kind=expression со ссылками @var:",
    VariableScenario.VAR_DEPENDENCY_TOPOSORT: "Зависимости @var: резолвятся топосортом",
    VariableScenario.FLOW_STATIC_LITERAL: "Flow-level литерал в flow.json",
    VariableScenario.FLOW_VAR_REFERENCE: "Flow-level @var:key ссылка на company-переменную",
    VariableScenario.BRANCH_VARIABLES_MERGE: "Branch override variables_mode=merge",
    VariableScenario.BRANCH_VARIABLES_REPLACE: "Branch override variables_mode=replace",
    VariableScenario.RUNTIME_METADATA_OVERRIDE: "metadata.variables переопределяет flow variables",
    VariableScenario.IDENTITY_VARIABLES: "user_id/company_id/active_namespace из контекста запроса",
    VariableScenario.PROMPT_TEMPLATE_RENDER: "Рендер {var}/{?var}/{var|default} в промптах",
    VariableScenario.MCP_HEADER_VAR_REF: "@var: в MCP headers",
    VariableScenario.PUBLIC_AGENT_CARD: "public=true в agent-card A2A",
    VariableScenario.LEDGER_VARIABLES_RESOLVED: "Audit variables_resolved без значений секретов",
    VariableScenario.VERSIONING: "Каждый upsert инкрементит version",
}


DEMO_VARIABLE_KEYS: dict[VariableScenario, str] = {
    VariableScenario.COMPANY_STATIC: "company_name",
    VariableScenario.COMPANY_SECRET_ENCRYPTED: "support_api_key",
    VariableScenario.SECRET_SHARED_FOR_EXECUTION: "support_api_key",
    VariableScenario.SECRET_PRIVATE_OWNER: "private_owner_token",
    VariableScenario.SCOPED_BY_NAMESPACE: "demo_greeting",
    VariableScenario.SCOPED_BY_USER_ID: "demo_user_tier",
    VariableScenario.SCOPED_BY_CHANNEL: "demo_channel_hint",
    VariableScenario.SCOPED_BY_VAR: "order_limit",
    VariableScenario.EXPRESSION_WITH_VAR_REFS: "signature",
    VariableScenario.VAR_DEPENDENCY_TOPOSORT: "base_url",
    VariableScenario.FLOW_STATIC_LITERAL: "max_response_length",
    VariableScenario.FLOW_VAR_REFERENCE: "company_name",
    VariableScenario.BRANCH_VARIABLES_MERGE: "max_response_length",
    VariableScenario.BRANCH_VARIABLES_REPLACE: "max_response_length",
}


__all__ = [
    "DEMO_VARIABLE_KEYS",
    "VARIABLE_SCENARIO_DESCRIPTIONS",
    "VariableScenario",
]
