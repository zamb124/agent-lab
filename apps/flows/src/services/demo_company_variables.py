"""Идемпотентный seed демо-company-переменных для example bundles.

Вызывается из ``init_company_resources`` после загрузки public flows: покрывает
сценарии из ``core.variables.scenarios`` (static/secret/scoped/expression).
"""

from __future__ import annotations

from pathlib import Path

from core.logging import get_logger
from core.secrets.models import VariableWriteRequest
from core.types import parse_json_object, require_json_array, require_json_object
from core.variables.service import VariablesService

logger = get_logger(__name__)

_SEED_PATH = Path(__file__).resolve().parent.parent.parent / "bundles" / "_seed" / "demo_company_variables.json"


def _load_seed_requests() -> list[VariableWriteRequest]:
    if not _SEED_PATH.is_file():
        raise FileNotFoundError(f"Demo variables seed не найден: {_SEED_PATH}")
    seed_root = parse_json_object(_SEED_PATH.read_text(encoding="utf-8"), "demo_company_variables.json")
    variables_raw = require_json_array(seed_root["variables"], "variables")
    requests: list[VariableWriteRequest] = []
    for index, entry_raw in enumerate(variables_raw):
        entry = require_json_object(entry_raw, f"variables[{index}]")
        requests.append(VariableWriteRequest.model_validate(entry))
    return requests


async def seed_demo_company_variables(
    variables_service: VariablesService,
    company_id: str,
) -> int:
    """Upsert демо-переменных компании. Возвращает число обработанных ключей."""
    requests = _load_seed_requests()
    seeded = 0
    for request in requests:
        _ = await variables_service.upsert(request)
        seeded += 1
    logger.info(
        "demo_company_variables_seeded",
        company_id=company_id,
        count=seeded,
    )
    return seeded


__all__ = ["seed_demo_company_variables"]
