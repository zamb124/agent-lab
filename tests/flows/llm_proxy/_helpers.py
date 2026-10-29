"""Хелперы HTTP-тестов OpenAI LLM proxy."""

from __future__ import annotations

from pathlib import Path

from apps.flows.di import FlowsDi
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.services.flows_loader import FlowsLoader, load_tools_to_db
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service

_FLOWS_ROOT = Path(__file__).resolve().parents[3] / "apps" / "flows"
_FLOWS_REGISTRY_PATH = _FLOWS_ROOT / "registry.yaml"
_FLOWS_BUNDLES_DIR = _FLOWS_ROOT / "bundles"

FLOWS_HTTP_BASE = "http://127.0.0.1:9001"
LLM_MODELS_PATH = "/flows/api/v1/llm/v1/models"
LLM_CHAT_COMPLETIONS_PATH = "/flows/api/v1/llm/v1/chat/completions"
LLM_IMAGES_GENERATIONS_PATH = "/flows/api/v1/llm/v1/images/generations"
LLM_ONLYOFFICE_PROXY_PATH = "/flows/api/v1/llm/v1/proxy"


def user_id_from_auth_token(auth_token: str) -> str:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("invalid auth token")
    return token_data.user_id


def company_id_from_auth_token(auth_token: str) -> str:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("invalid auth token")
    return token_data.company_id


async def ensure_company_public_flows(company_id: str, di: FlowsDi) -> None:
    """Материализует flow ``lara`` в компании токена. Компания ``system`` не используется."""
    if not company_id.strip():
        raise AssertionError("company_id обязателен")
    if company_id == "system":
        raise AssertionError("seed lara в company system запрещён в LLM proxy тестах")
    company = await Company.get(company_id)
    if company is None:
        raise AssertionError(f"company {company_id} not found")
    if company.owner_user_id is None or not company.owner_user_id.strip():
        raise AssertionError(f"company {company_id} без owner_user_id")
    owner = await User.get(company.owner_user_id)
    if owner is None:
        raise AssertionError(
            f"owner {company.owner_user_id!r} компании {company_id} не найден"
        )
    if company_id not in owner.companies:
        raise AssertionError(
            f"owner {owner.user_id} не состоит в company {company_id}"
        )

    token = set_context(
        Context(
            user=owner,
            host="test",
            session_id=f"ensure_public_flows_{company_id}",
            channel="test",
            language=Language.RU,
            active_company=company,
            user_companies=[company],
            trace_id=f"test:ensure_public_flows:{company_id}",
        )
    )
    try:
        existing_lara = await FlowConfig.current_for_flow("lara")
        if existing_lara is not None:
            return
        _ = await load_tools_to_db(flow_access_service=di.flow_access_service)
        loader = FlowsLoader(
            bundles_dir=_FLOWS_BUNDLES_DIR,
            registry_path=_FLOWS_REGISTRY_PATH,
            flow_access_service=di.flow_access_service,
        )
        loaded_flow_id = await loader.reload_flow_bundle("lara")
        if loaded_flow_id != "lara":
            raise AssertionError(
                f"ожидали reload lara, получили {loaded_flow_id!r} для company {company_id}"
            )
        lara_after = await FlowConfig.current_for_flow("lara")
        if lara_after is None:
            raise AssertionError(f"flow lara отсутствует в company {company_id} после seed")
    finally:
        reset_context(token)
