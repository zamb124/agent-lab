"""Интеграционные тесты /frontend/api/auth/grafana-check (Traefik ForwardAuth → Grafana auth.proxy)."""

import pytest


class TestGrafanaAuthCheck:
    @pytest.mark.asyncio
    async def test_grafana_check_system_user_grafana_host_returns_200_with_header(
        self, frontend_client, auth_token_system
    ) -> None:
        frontend_client.cookies.set("auth_token", auth_token_system)
        response = await frontend_client.get(
            "/frontend/api/auth/grafana-check",
            headers={"Host": "grafana.humanitec.ru"},
        )
        assert response.status_code == 200
        assert "X-Auth-User" in response.headers
        assert response.headers["X-Auth-User"]

    @pytest.mark.asyncio
    async def test_grafana_check_non_system_returns_403(
        self, frontend_client, auth_token_company2
    ) -> None:
        frontend_client.cookies.set("auth_token", auth_token_company2)
        response = await frontend_client.get(
            "/frontend/api/auth/grafana-check",
            headers={"Host": "grafana.humanitec.ru"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_grafana_check_no_token_returns_401(self, frontend_client) -> None:
        response = await frontend_client.get(
            "/frontend/api/auth/grafana-check",
            headers={"Host": "grafana.humanitec.ru"},
        )
        assert response.status_code == 401
