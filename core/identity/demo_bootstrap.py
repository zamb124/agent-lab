"""Bootstrap демо-компании и пользователя для App Review (auth.demo)."""

from __future__ import annotations

import uuid

from core.auth.utils import hash_password
from core.clients import ServiceClient
from core.clients.service_client import ServiceClientError
from core.config import get_settings
from core.context import clear_context, set_context
from core.logging import get_logger
from core.models.context_models import Context, Language
from core.models.identity_models import Company, User, UserStatus
from core.utils.tokens import get_token_service

logger = get_logger(__name__)

DEMO_OWNER_ROLES = ["owner", "admin"]


def _normalize_email(value: str) -> str:
    return value.strip().lower()


async def ensure_demo_company_and_user(container: object) -> None:
    """
    Создаёт или обновляет компанию и пользователя из settings.auth.demo.
    Не вызывать при login_enabled=False.
    """
    settings = get_settings()
    demo = settings.auth.demo

    if not demo.login_enabled:
        return

    password = demo.password
    if password is None or password == "":
        raise ValueError(
            "auth.demo.login_enabled=true, но пароль пустой: задайте AUTH__DEMO__PASSWORD"
        )

    company_repo = container.company_repository
    user_repo = container.user_repository
    subdomain_repo = container.subdomain_repository

    email_norm = _normalize_email(demo.email)
    company_id = demo.company_id
    subdomain = demo.subdomain
    company_name = demo.company_name

    company = await company_repo.get(company_id)
    if company is None:
        company = Company(
            company_id=company_id,
            name=company_name,
            subdomain=subdomain,
            members={},
            status="active",
        )
        logger.info("Demo bootstrap: создана компания %s", company_id)
    else:
        updated = False
        if company.name != company_name:
            company.name = company_name
            updated = True
        if company.subdomain != subdomain:
            company.subdomain = subdomain
            updated = True
        if company.status != "active":
            company.status = "active"
            updated = True
        if updated:
            logger.info("Demo bootstrap: обновлены поля компании %s", company_id)

    users = await user_repo.list(limit=10000)
    matched = [
        u
        for u in users
        if any(_normalize_email(e) == email_norm for e in u.emails)
    ]
    if len(matched) > 1:
        raise ValueError(
            f"Несколько пользователей с email {demo.email}: "
            f"{', '.join(u.user_id for u in matched)}"
        )

    pw_hash = hash_password(password)

    if matched:
        user = matched[0]
        user.name = user.name or "Demo"
        user.status = UserStatus.ACTIVE
        if demo.email not in user.emails:
            user.emails = [*user.emails, demo.email]
        user.password_hash = pw_hash
        user.active_company_id = company_id
        roles = user.companies.get(company_id, [])
        merged_roles = list(dict.fromkeys([*roles, *DEMO_OWNER_ROLES]))
        user.companies[company_id] = merged_roles
        logger.info("Demo bootstrap: обновлён пользователь %s", user.user_id)
    else:
        user_id = f"user_demo_{uuid.uuid4().hex[:12]}"
        user = User(
            user_id=user_id,
            name="Demo",
            status=UserStatus.ACTIVE,
            emails=[demo.email],
            password_hash=pw_hash,
            active_company_id=company_id,
            companies={company_id: list(DEMO_OWNER_ROLES)},
        )
        logger.info("Demo bootstrap: создан пользователь %s", user_id)

    company.owner_user_id = user.user_id
    member_roles = company.members.get(user.user_id, [])
    merged_member = list(dict.fromkeys([*member_roles, *DEMO_OWNER_ROLES]))
    company.members[user.user_id] = merged_member

    await company_repo.set(company)
    await subdomain_repo.set_mapping(subdomain, company_id)
    await user_repo.set(user)

    roles = user.companies.get(company_id, [])
    auth_token = get_token_service().create_token(
        user_id=user.user_id,
        company_id=company_id,
        roles=roles,
        email=user.email,
    )
    init_context = Context(
        user=User(
            user_id=user.user_id,
            name=user.name or user.user_id,
            groups=user.groups,
        ),
        host="internal",
        session_id="demo-bootstrap",
        channel="system",
        language=Language.RU,
        active_company=Company(
            company_id=company.company_id,
            name=company.name,
            subdomain=company.subdomain,
        ),
        user_companies=[],
        trace_id=f"frontend:demo-bootstrap:{uuid.uuid4()}",
        auth_token=auth_token,
    )

    service_client = ServiceClient()
    set_context(init_context)
    try:
        init_response = await service_client.post(
            "flows",
            "/flows/api/v1/company/init",
            json={
                "company_id": company_id,
                "company_name": company_name,
                "subdomain": subdomain,
            },
        )
        logger.info(
            "Demo bootstrap: flows company/init для %s: task_id=%s",
            company_id,
            init_response.get("task_id"),
        )
    except ServiceClientError as exc:
        logger.error(
            "Demo bootstrap: не удалось вызвать flows company/init для %s: %s",
            company_id,
            exc,
        )
    except Exception as exc:
        logger.error(
            "Demo bootstrap: не удалось вызвать flows company/init для %s: %s",
            company_id,
            exc,
            exc_info=True,
        )
    finally:
        clear_context()
