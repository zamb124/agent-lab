"""У каждой зарегистрированной CRM-интеграции есть SVG в UI (см. IntegrationRegistry._register)."""

from __future__ import annotations

from pathlib import Path


def test_each_registered_integration_has_svg(crm_container) -> None:
    root = Path(__file__).resolve().parents[2] / "apps" / "crm" / "ui" / "assets" / "integrations"
    for provider_id in crm_container.integration_registry.known_provider_ids():
        path = root / f"{provider_id}.svg"
        assert path.is_file(), f"Ожидается иконка: {path}"
