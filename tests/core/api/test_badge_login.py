"""Вход по бейджу сотрудника — платформенный для любых терминалов.

`UserBadge` — тенантный credential ``(company_id, code) → user_id`` в
``platform_shared``; `BadgeService` резолвит код и делегирует сессию
``AuthService.login_badge``. HTTP-граница — общий ``/{svc}/api/auth/login/badge``
на любом сервисе; анонимный RouteRule уже покрывает ``*/api/auth/login/*``.
Тесты идут по продовому пути: реальная таблица, реальный AuthMiddleware,
реальный Redis rate-limit.
"""

from __future__ import annotations

import pytest
from httpx2 import ASGITransport, AsyncClient

from core.errors.boundary import (
    PlatformAccessDeniedError,
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.models.identity_models import User, UserBadge
from core.models.identity_models.contracts import AuthProvider

_COMPANY = "system"
_MEMBER = "test_user"
_BADGE_PATH = "/frontend/api/auth/login/badge"
_ME_PATH = "/frontend/api/auth/me"


class TestUserBadgeModel:
    """Привязка: единственная точка записи credential'а."""

    async def test_bind_same_code_same_user_is_idempotent(
        self, unique_id: str
    ) -> None:
        """Повторная привязка того же кода тому же сотруднику — no-op."""
        first = await UserBadge.bind(
            company_id=_COMPANY, code=f"BDG-{unique_id}", user_id=_MEMBER
        )
        second = await UserBadge.bind(
            company_id=_COMPANY, code=f"BDG-{unique_id}", user_id=_MEMBER
        )
        assert second.badge_id == first.badge_id

    async def test_bind_same_code_other_user_then_conflict(
        self, unique_id: str
    ) -> None:
        """Код занят чужим сотрудником — badge_conflict, без тихого перехвата."""
        _ = await UserBadge.bind(
            company_id=_COMPANY, code=f"CNF-{unique_id}", user_id=_MEMBER
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await UserBadge.bind(
                company_id=_COMPANY,
                code=f"CNF-{unique_id}",
                user_id=f"other-{unique_id}",
            )
        assert exc.value.error_code == "badge_conflict"

    async def test_bind_empty_code_then_conflict(self) -> None:
        with pytest.raises(PlatformConflictError) as exc:
            _ = await UserBadge.bind(company_id=_COMPANY, code="  ", user_id=_MEMBER)
        assert exc.value.error_code == "badge_empty"

    async def test_unbind_removes_badge(self, unique_id: str) -> None:
        """Отозванный бейдж больше не резолвится."""
        _ = await UserBadge.bind(
            company_id=_COMPANY, code=f"RVK-{unique_id}", user_id=_MEMBER
        )
        deleted = await UserBadge.unbind(_COMPANY, f"RVK-{unique_id}")
        assert deleted == 1
        assert await UserBadge.resolve(_COMPANY, f"RVK-{unique_id}") is None


class TestBadgeService:
    """Резолв + членство + rate-limit — сервисный уровень."""

    async def test_login_badge_with_valid_badge_then_session(
        self, frontend_di, unique_id: str
    ) -> None:
        """Бейдж члена компании → SESSION JWT и активная компания."""
        _ = await UserBadge.bind(
            company_id=_COMPANY, code=f"BDG-{unique_id}", user_id=_MEMBER
        )

        result = await frontend_di.badge_service.login_badge(
            company_id=_COMPANY,
            code=f"BDG-{unique_id}",
            client_ip=f"10.10.{int(unique_id[:4], 16) % 250 + 1}.1",
        )

        assert result.success is True
        assert result.user is not None and result.user.user_id == _MEMBER
        assert result.session is not None
        assert result.session.provider == AuthProvider.BADGE
        assert result.session.user_id == _MEMBER
        assert result.token is not None and result.token.count(".") == 2
        assert result.user.active_company_id == _COMPANY

    async def test_login_badge_with_unknown_code_then_not_found(
        self, frontend_di, unique_id: str
    ) -> None:
        with pytest.raises(PlatformNotFoundError) as exc:
            await frontend_di.badge_service.login_badge(
                company_id=_COMPANY, code=f"NOPE-{unique_id}", client_ip=""
            )
        assert exc.value.error_code == "badge_not_found"

    async def test_login_badge_with_blank_code_then_not_found(
        self, frontend_di
    ) -> None:
        """Пробельный скан (грязный HID-кадр) — badge_not_found, не 500."""
        with pytest.raises(PlatformNotFoundError) as exc:
            await frontend_di.badge_service.login_badge(
                company_id=_COMPANY, code="   ", client_ip=""
            )
        assert exc.value.error_code == "badge_not_found"

    async def test_login_badge_with_dead_owner_then_owner_not_found(
        self, frontend_di, unique_id: str
    ) -> None:
        """Бейдж жив, а user удалён — отдельный код badge_owner_not_found."""
        _ = await UserBadge.bind(
            company_id=_COMPANY,
            code=f"GHOST-{unique_id}",
            user_id=f"ghost-{unique_id}",
        )
        with pytest.raises(PlatformNotFoundError) as exc:
            await frontend_di.badge_service.login_badge(
                company_id=_COMPANY, code=f"GHOST-{unique_id}", client_ip=""
            )
        assert exc.value.error_code == "badge_owner_not_found"

    async def test_login_badge_without_membership_then_denied(
        self, frontend_di, unique_id: str
    ) -> None:
        """Сотрудник существует, но не член компании — badge_login_denied."""
        outsider_id = f"outsider-{unique_id}"
        _ = await User.set(
            User(
                user_id=outsider_id,
                name=f"Outsider {unique_id}",
                emails=[f"{outsider_id}@test.local"],
                companies={},
                active_company_id="",
            )
        )
        _ = await UserBadge.bind(
            company_id=_COMPANY, code=f"OUT-{unique_id}", user_id=outsider_id
        )
        with pytest.raises(PlatformAccessDeniedError) as exc:
            await frontend_di.badge_service.login_badge(
                company_id=_COMPANY, code=f"OUT-{unique_id}", client_ip=""
            )
        assert exc.value.error_code == "badge_login_denied"

    async def test_login_badge_rate_limited_after_burst(
        self, frontend_di, unique_id: str
    ) -> None:
        """30 промахов с одного IP — 31-й отсекается rate-limit'ом."""
        ip = f"172.30.{int(unique_id[:4], 16) % 250 + 1}.7"
        for _ in range(30):
            with pytest.raises(PlatformNotFoundError):
                await frontend_di.badge_service.login_badge(
                    company_id=_COMPANY, code=f"RL-{unique_id}", client_ip=ip
                )
        with pytest.raises(PlatformAccessDeniedError) as exc:
            await frontend_di.badge_service.login_badge(
                company_id=_COMPANY, code=f"RL-{unique_id}", client_ip=ip
            )
        assert exc.value.error_code == "badge_login_rate_limited"


class TestResolveLoginCompany:
    """Tenant по Host: только поддомен компании открывает вход."""

    async def test_resolve_login_company_with_subdomain_then_company(
        self, frontend_di
    ) -> None:
        company = await frontend_di.badge_service.resolve_login_company(
            "system.lvh.me"
        )
        assert company.company_id == _COMPANY

    async def test_resolve_login_company_without_subdomain_then_denied(
        self, frontend_di
    ) -> None:
        with pytest.raises(PlatformAccessDeniedError) as exc:
            await frontend_di.badge_service.resolve_login_company("lvh.me")
        assert exc.value.error_code == "badge_company_required"

    async def test_resolve_login_company_with_infra_host_then_denied(
        self, frontend_di
    ) -> None:
        """Инфраструктурный поддомен (grafana) — не компания."""
        with pytest.raises(PlatformAccessDeniedError) as exc:
            await frontend_di.badge_service.resolve_login_company(
                "grafana.lvh.me"
            )
        assert exc.value.error_code == "badge_company_required"

    async def test_resolve_login_company_with_unknown_slug_then_not_found(
        self, frontend_di, unique_id: str
    ) -> None:
        with pytest.raises(PlatformNotFoundError) as exc:
            await frontend_di.badge_service.resolve_login_company(
                f"co-{unique_id}.lvh.me"
            )
        assert exc.value.error_code == "badge_company_not_found"


class TestBadgeLoginRest:
    """HTTP-граница: анонимный POST, куки сессии, изоляция тенантов."""

    async def test_login_via_company_subdomain_then_session_cookies(
        self, frontend_client: AsyncClient, frontend_di, unique_id: str
    ) -> None:
        """Полный цикл: POST → куки → JWT реально открывает auth-роут."""
        _ = frontend_di
        _ = await UserBadge.bind(
            company_id=_COMPANY, code=f"RST-{unique_id}", user_id=_MEMBER
        )
        resp = await frontend_client.post(
            _BADGE_PATH,
            json={"code": f"RST-{unique_id}"},
            headers={"host": "system.lvh.me"},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["user_id"] == _MEMBER
        assert body["company_id"] == _COMPANY
        assert body["display_name"] == _MEMBER
        cookies = resp.headers.get_list("set-cookie")
        assert any(c.startswith("session_id=") for c in cookies)
        assert any(c.startswith("auth_token=") for c in cookies)

        token = next(
            c.split("auth_token=", 1)[1].split(";", 1)[0]
            for c in cookies
            if c.startswith("auth_token=")
        )
        authed = await frontend_client.get(
            _ME_PATH,
            headers={
                "host": "system.lvh.me",
                "Authorization": f"Bearer {token}",
            },
        )
        assert authed.status_code == 200, authed.text
        assert authed.json()["user_id"] == _MEMBER

    async def test_login_on_stock_service_then_cookies(
        self, stock_app, stock_di, unique_id: str
    ) -> None:
        """Тот же роут живёт на stock-процессе — терминал бьёт в свой порт."""
        _ = stock_di
        _ = await UserBadge.bind(
            company_id=_COMPANY, code=f"STK-{unique_id}", user_id=_MEMBER
        )
        async with AsyncClient(
            transport=ASGITransport(app=stock_app),
            base_url="http://system.lvh.me",
        ) as client:
            resp = await client.post(
                "/stock/api/auth/login/badge",
                json={"code": f"STK-{unique_id}"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["user_id"] == _MEMBER
        cookies = resp.headers.get_list("set-cookie")
        assert any(c.startswith("auth_token=") for c in cookies)

    async def test_login_without_subdomain_then_forbidden(
        self, frontend_client: AsyncClient, unique_id: str
    ) -> None:
        """Базовый домен без субдомена — badge_company_required → 403."""
        resp = await frontend_client.post(
            _BADGE_PATH,
            json={"code": f"ANY-{unique_id}"},
            headers={"host": "lvh.me"},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["error_code"] == "badge_company_required"

    async def test_login_badge_of_other_company_then_not_found(
        self, frontend_client: AsyncClient, frontend_di, unique_id: str
    ) -> None:
        """Бейдж system на поддомене company2 — badge_not_found: индекс
        бейджей строго тенантный, утечки между компаниями нет."""
        _ = frontend_di
        _ = await UserBadge.bind(
            company_id=_COMPANY, code=f"XCO-{unique_id}", user_id=_MEMBER
        )
        resp = await frontend_client.post(
            _BADGE_PATH,
            json={"code": f"XCO-{unique_id}"},
            headers={"host": "company2.lvh.me"},
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error_code"] == "badge_not_found"

    async def test_login_with_missing_code_then_422(
        self, frontend_client: AsyncClient
    ) -> None:
        resp = await frontend_client.post(
            _BADGE_PATH, json={}, headers={"host": "system.lvh.me"}
        )
        assert resp.status_code == 422, resp.text

    async def test_login_with_empty_code_then_422(
        self, frontend_client: AsyncClient
    ) -> None:
        resp = await frontend_client.post(
            _BADGE_PATH, json={"code": ""}, headers={"host": "system.lvh.me"}
        )
        assert resp.status_code == 422, resp.text

    async def test_login_with_blank_code_then_not_found(
        self, frontend_client: AsyncClient
    ) -> None:
        """Пробелы проходят min_length, но сервис отвечает badge_not_found."""
        resp = await frontend_client.post(
            _BADGE_PATH, json={"code": "   "}, headers={"host": "system.lvh.me"}
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error_code"] == "badge_not_found"

    async def test_login_unknown_badge_then_not_found_json(
        self, frontend_client: AsyncClient, unique_id: str
    ) -> None:
        """Неизвестный бейдж — конверт ошибки с error_code, а не stack-trace."""
        resp = await frontend_client.post(
            _BADGE_PATH,
            json={"code": f"UNKN-{unique_id}"},
            headers={"host": "system.lvh.me"},
        )
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert body["error_code"] == "badge_not_found"
        assert "error_detail" in body


_BADGES_PATH = "/frontend/api/team/badges"


class TestBadgeAdminRest:
    """Управление бейджами — REST-зеркало frontend/badges/*_requested.

    Check `company` admin: привязка/отзыв делает консоль компании,
    а не оператор терминала.
    """

    async def test_bind_then_badge_login_end_to_end(
        self,
        frontend_client: AsyncClient,
        auth_headers_system: dict[str, str],
        unique_id: str,
    ) -> None:
        """Золотой путь консоли: admin привязал бейдж → сотрудник вошёл."""
        bind = await frontend_client.post(
            _BADGES_PATH,
            json={"user_id": _MEMBER, "code": f"E2E-{unique_id}"},
            headers=auth_headers_system,
        )
        assert bind.status_code == 200, bind.text
        badge = bind.json()
        assert badge["code"] == f"E2E-{unique_id}"
        assert badge["user_id"] == _MEMBER
        assert badge["user_name"] == _MEMBER

        listed = await frontend_client.get(
            _BADGES_PATH,
            params={"user_id": _MEMBER},
            headers=auth_headers_system,
        )
        assert listed.status_code == 200, listed.text
        assert any(
            row["badge_id"] == badge["badge_id"] for row in listed.json()["items"]
        )

        login = await frontend_client.post(
            _BADGE_PATH,
            json={"code": f"E2E-{unique_id}"},
            headers={"host": "system.lvh.me"},
        )
        assert login.status_code == 200, login.text

        unbind = await frontend_client.delete(
            f"{_BADGES_PATH}/{badge['badge_id']}", headers=auth_headers_system
        )
        assert unbind.status_code == 200, unbind.text

        relogin = await frontend_client.post(
            _BADGE_PATH,
            json={"code": f"E2E-{unique_id}"},
            headers={"host": "system.lvh.me"},
        )
        assert relogin.status_code == 404, relogin.text

    async def test_bind_duplicate_code_other_user_then_conflict(
        self,
        frontend_client: AsyncClient,
        auth_headers_system: dict[str, str],
        unique_id: str,
    ) -> None:
        _ = await frontend_client.post(
            _BADGES_PATH,
            json={"user_id": _MEMBER, "code": f"DUP-{unique_id}"},
            headers=auth_headers_system,
        )
        outsider_id = f"member-{unique_id}"
        _ = await User.set(
            User(
                user_id=outsider_id,
                name=f"Member {unique_id}",
                emails=[f"{outsider_id}@test.local"],
                companies={_COMPANY: ["viewer"]},
                active_company_id=_COMPANY,
            )
        )
        resp = await frontend_client.post(
            _BADGES_PATH,
            json={"user_id": outsider_id, "code": f"DUP-{unique_id}"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error_code"] == "badge_conflict"

    async def test_bind_non_member_user_then_forbidden(
        self,
        frontend_client: AsyncClient,
        auth_headers_system: dict[str, str],
        unique_id: str,
    ) -> None:
        outsider_id = f"nomem-{unique_id}"
        _ = await User.set(
            User(
                user_id=outsider_id,
                name=f"Nomem {unique_id}",
                emails=[f"{outsider_id}@test.local"],
                companies={},
                active_company_id="",
            )
        )
        resp = await frontend_client.post(
            _BADGES_PATH,
            json={"user_id": outsider_id, "code": f"NM-{unique_id}"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["error_code"] == "badge_user_not_member"

    async def test_bind_unknown_user_then_not_found(
        self,
        frontend_client: AsyncClient,
        auth_headers_system: dict[str, str],
        unique_id: str,
    ) -> None:
        resp = await frontend_client.post(
            _BADGES_PATH,
            json={"user_id": f"ghost-{unique_id}", "code": f"GU-{unique_id}"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error_code"] == "badge_user_not_found"

    async def test_unbind_unknown_badge_then_not_found(
        self,
        frontend_client: AsyncClient,
        auth_headers_system: dict[str, str],
        unique_id: str,
    ) -> None:
        resp = await frontend_client.delete(
            f"{_BADGES_PATH}/ubg-{unique_id}", headers=auth_headers_system
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error_code"] == "badge_not_found"

    async def test_bind_without_admin_then_forbidden(
        self,
        frontend_client: AsyncClient,
        auth_headers_system_user2: dict[str, str],
        unique_id: str,
    ) -> None:
        """Member без admin-роли не управляет бейджами — Check `company` admin."""
        resp = await frontend_client.post(
            _BADGES_PATH,
            json={"user_id": _MEMBER, "code": f"NADM-{unique_id}"},
            headers=auth_headers_system_user2,
        )
        assert resp.status_code == 403, resp.text

    async def test_bind_without_session_then_unauthorized(
        self, frontend_client: AsyncClient, unique_id: str
    ) -> None:
        resp = await frontend_client.post(
            _BADGES_PATH,
            json={"user_id": _MEMBER, "code": f"NOAUTH-{unique_id}"},
        )
        assert resp.status_code in (401, 403), resp.text
