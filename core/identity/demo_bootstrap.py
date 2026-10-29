"""Bootstrap демо-компании и пользователя для App Review (auth.demo)."""

from __future__ import annotations

import uuid

from core.auth.utils import hash_password
from core.authz.company_sync import sync_company_member_roles
from core.authz.service import AuthzService
from core.clients.service_client import ServiceClient
from core.config import get_settings
from core.context import reset_context, set_context
from core.logging import get_logger
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User, UserStatus
from core.utils.tokens import get_token_service

logger = get_logger(__name__)

DEMO_OWNER_ROLES = ["owner", "admin"]


async def ensure_demo_company_and_user(
    *,
    authz: AuthzService,
) -> None:
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
            'auth.demo.login_enabled=true but password is empty: set AUTH__DEMO__PASSWORD'
        )

    company_id = demo.company_id
    subdomain = demo.subdomain
    company_name = demo.company_name

    company = await Company.get(company_id)
    if company is None:
        company = Company(
            company_id=company_id,
            name=company_name,
            subdomain=subdomain,
            members={},
            status="active",
        )
        logger.info("identity.demo.bootstrap", company_id=company_id)
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
            logger.info("identity.demo.bootstrap", company_id=company_id)

    matched = await User.list_containing_email_ci_by_user_id_asc(demo.email)
    if len(matched) > 1:
        raise ValueError(
            f"Multiple users with email {demo.email}: "
            + f"{', '.join(u.user_id for u in matched)}"
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
        logger.info("identity.demo.bootstrap", user_id=user.user_id)
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
        logger.info("identity.demo.bootstrap", user_id=user_id)

    company.owner_user_id = user.user_id
    member_roles = company.members.get(user.user_id, [])
    merged_member = list(dict.fromkeys([*member_roles, *DEMO_OWNER_ROLES]))
    company.members[user.user_id] = merged_member

    _ = await Company.set(company)
    _ = await User.set(user)
    await sync_company_member_roles(
        authz,
        company_id=company_id,
        user_id=user.user_id,
        roles=merged_member,
    )

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
    init_context_token = set_context(init_context)
    try:
        init_response = await service_client.post(
            "flows",
            "/flows/api/v1/internal/company/init",
            json={
                "company_id": company_id,
                "company_name": company_name,
                "subdomain": subdomain,
            },
        )
        if not isinstance(init_response, dict):
            raise ValueError("flows company/init response must be JSON object")
        task_id = init_response.get("task_id")
        if not isinstance(task_id, str) or task_id == "":
            raise ValueError("flows company/init response.task_id required")
        logger.info("identity.demo.bootstrap.flows.company.init", company_id=company_id, task_id=task_id)
    finally:
        reset_context(init_context_token)
