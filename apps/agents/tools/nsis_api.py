"""
NSIS API - инструмент для проверки полисов ОСАГО в базе НСИС.
"""

from typing import Optional

from apps.agents.src.tools import tool


def _nsis_mock(args: dict) -> dict:
    """Mock для NSIS API."""
    policy_number = args.get("policy_number", "")
    vin = args.get("vin")
    
    if "INVALID" in policy_number.upper():
        return {"status": "not_found", "message": "Полис не найден в базе НСИС"}
    elif "EXPIRED" in policy_number.upper():
        return {
            "status": "expired",
            "policy_number": policy_number,
            "valid_from": "2023-01-15",
            "valid_to": "2024-01-14",
            "insurance_company": "РЕСО-Гарантия",
            "vehicle_vin": vin or "XTA21214052123456",
            "owner": "Петров П.П.",
        }
    else:
        return {
            "status": "valid",
            "policy_number": policy_number,
            "valid_from": "2024-01-15",
            "valid_to": "2025-01-14",
            "insurance_company": "Ингосстрах",
            "vehicle_vin": vin or "XTA21214052123456",
            "owner": "Иванов И.И.",
        }


@tool(
    name="nsis_api",
    description="Проверяет полис ОСАГО в базе НСИС. Возвращает статус полиса, срок действия и страховую компанию.",
    tags=["api"],
    mock_response=_nsis_mock,
)
async def nsis_api(
    policy_number: str,
    vin: str = None,
    state: Optional[dict] = None,
) -> dict:
    """Запрос к реальному API НСИС."""
    raise NotImplementedError("Реальная интеграция с NSIS API не реализована")
