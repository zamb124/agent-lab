"""
API для управления компаниями
"""

import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from apps.frontend.dependencies import ContainerDep
from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.tasks.task_names import TASK_INIT_NEW_COMPANY
from core.api.companies import CompanyMembershipResponse, build_my_companies_response
from core.config import get_settings
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.logging import get_logger
from core.models.identity_models import Company, User
from core.pagination import ListResponse
from core.tasks.kicker import kiq_task_name_with_context
from core.utils.domain import build_url, get_cookie_domain
from core.utils.subdomain import validate_slug
from core.utils.tokens import TokenService, get_token_service

logger = get_logger(__name__)
router = APIRouter(prefix="/api/companies", tags=["public", "companies"])


class CheckSlugRequest(BaseModel):
    slug: str


class CheckSlugResponse(BaseModel):
    available: bool
    slug: str


class CreateCompanyRequest(BaseModel):
    name: str
    slug: str


class CreateCompanyResponse(BaseModel):
    company_id: str
    name: str
    subdomain: str
    redirect_url: str


class SystemAccessRequest(BaseModel):
    role: str


class SystemAccessGrantedResponse(BaseModel):
    success: bool
    company_id: str
    roles: list[str]


_SYSTEM_ASSIGNABLE_ROLES: tuple[str, ...] = ("admin", "developer", "viewer")


def _require_authenticated_user(request: Request) -> User:
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    return request.state.user


def _ensure_user_is_system_member(user: User) -> None:
    if SYSTEM_COMPANY_ID not in user.companies:
        raise HTTPException(
            status_code=403, detail="Доступно только для участников компании system"
        )


@router.post("/check-slug", response_model=CheckSlugResponse)
async def check_slug(request: CheckSlugRequest, container: ContainerDep):
    """
    Проверка доступности slug для субдомена

    Args:
        request: Запрос с slug
        container: DI контейнер

    Returns:
        Информация о доступности slug
    """
    slug = request.slug.lower().strip()

    is_valid, error = validate_slug(slug)
    if not is_valid:
        return CheckSlugResponse(available=False, slug=slug)

    subdomain_repo = container.subdomain_repository
    company_id = await subdomain_repo.get_company_id(slug)

    return CheckSlugResponse(available=company_id is None, slug=slug)


@router.post("", response_model=CreateCompanyResponse)
async def create_company(
    request_data: CreateCompanyRequest, request: Request, container: ContainerDep
):
    """
    Создание новой компании

    Args:
        request_data: Данные компании
        request: FastAPI request
        container: DI контейнер

    Returns:
        Информация о созданной компании и URL для редиректа
    """
    settings = get_settings()

    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")

    user = request.state.user
    name = request_data.name.strip()
    slug = request_data.slug.lower().strip()

    if not name:
        raise HTTPException(status_code=400, detail="Название компании обязательно")

    is_valid, error = validate_slug(slug)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    subdomain_repo = container.subdomain_repository
    company_repo = container.company_repository
    user_repo = container.user_repository

    existing_company_id = await subdomain_repo.get_company_id(slug)
    if existing_company_id:
        raise HTTPException(status_code=400, detail="Этот адрес уже занят")

    company_id = str(uuid.uuid4())
    logger.info(
        "frontend.company_create_started",
        name=name,
        slug=slug,
        company_id=company_id,
        owner_user_id=user.user_id,
    )

    company = Company(
        company_id=company_id,
        name=name,
        subdomain=slug,
        owner_user_id=user.user_id,
        status="active",
        members={user.user_id: ["owner"]},
        metadata={"initialization_status": "pending"},
    )

    await company_repo.set(company)
    logger.info(
        "frontend.company_created",
        company_id=company.company_id,
        company_subdomain=slug,
    )

    await subdomain_repo.set_mapping(slug, company.company_id)
    logger.info(
        "frontend.subdomain_registered",
        company_subdomain=slug,
        company_id=company.company_id,
    )

    # Проверяем что маппинг сохранился
    check_company_id = await subdomain_repo.get_company_id(slug)
    logger.info(
        "frontend.subdomain_mapping_checked",
        company_subdomain=slug,
        company_id=check_company_id,
    )

    if company.company_id not in user.companies:
        user.companies[company.company_id] = ["owner"]  # Список ролей, а не строка!
        user.active_company_id = company.company_id
        await user_repo.set(user)
        logger.info(
            "frontend.company_owner_added",
            user_id=user.user_id,
            company_id=company.company_id,
        )

    init_task = await kiq_task_name_with_context(
        TASK_INIT_NEW_COMPANY,
        idle_broker,
        company_id=company_id,
        company_name=name,
        subdomain=slug,
        owner_user_id=user.user_id,
    )
    logger.info(
        "frontend.company_init_task_enqueued",
        company_id=company_id,
        taskiq_task_id=init_task.task_id,
    )

    redirect_url = build_url(request.headers.get("host", ""), "/dashboard", slug)
    logger.info("frontend.company_create_redirect", redirect_url=redirect_url)

    # Перевыпускаем токен с company_id
    token_service = get_token_service()
    new_token = token_service.create_token(user.user_id, company.company_id, email=user.email)
    logger.info("frontend.session_token_reissued", company_id=company.company_id)

    # Обновляем cookie
    cookie_domain = get_cookie_domain(request.headers.get("host", ""))
    is_production = settings.server.env == "production"

    response = JSONResponse(
        content={
            "company_id": company.company_id,
            "name": company.name,
            "subdomain": company.subdomain,
            "redirect_url": redirect_url,
        }
    )

    response.set_cookie(
        key="auth_token",
        value=new_token,
        domain=cookie_domain,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=TokenService.SESSION_EXPIRES,
    )

    return response


@router.get("/me", response_model=ListResponse[CompanyMembershipResponse])
async def get_my_companies(
    request: Request,
    container: ContainerDep,
) -> ListResponse[CompanyMembershipResponse]:
    """Возвращает компании текущего пользователя с subdomain и ролями."""
    token_data = getattr(request.state, "token_data", None)
    if token_data is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await container.user_repository.get(token_data.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return await build_my_companies_response(
        user=user,
        company_repository=container.company_repository,
    )


@router.post("/{company_id}/system-access", response_model=SystemAccessGrantedResponse)
async def enter_company_as_system_member(
    company_id: str,
    payload: SystemAccessRequest,
    request: Request,
    container: ContainerDep,
) -> SystemAccessGrantedResponse:
    user = _require_authenticated_user(request)
    _ensure_user_is_system_member(user)

    target_company_id = company_id.strip()
    if not target_company_id:
        raise HTTPException(status_code=422, detail="company_id не может быть пустым")
    if target_company_id == SYSTEM_COMPANY_ID:
        raise HTTPException(
            status_code=400, detail="Нельзя изменять доступ к компании system через этот endpoint"
        )

    role = payload.role.strip()
    if role not in _SYSTEM_ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимая роль: {role}. Разрешено: {', '.join(_SYSTEM_ASSIGNABLE_ROLES)}",
        )

    company_repo = container.company_repository
    user_repo = container.user_repository
    target_company = await company_repo.get(target_company_id)
    if target_company is None:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    existing_roles = target_company.members.get(user.user_id, [])
    if role not in existing_roles:
        target_company.members[user.user_id] = [*existing_roles, role]
        await company_repo.set(target_company)
    else:
        target_company.members[user.user_id] = existing_roles

    user_roles = user.companies.get(target_company_id, [])
    if role not in user_roles:
        user.companies[target_company_id] = [*user_roles, role]
        await user_repo.set(user)
    else:
        user.companies[target_company_id] = user_roles

    return SystemAccessGrantedResponse(
        success=True,
        company_id=target_company_id,
        roles=user.companies[target_company_id],
    )


@router.delete("/{company_id}/system-access")
async def leave_company_as_system_member(
    company_id: str,
    request: Request,
    container: ContainerDep,
) -> JSONResponse:
    user = _require_authenticated_user(request)
    _ensure_user_is_system_member(user)

    target_company_id = company_id.strip()
    if not target_company_id:
        raise HTTPException(status_code=422, detail="company_id не может быть пустым")
    if target_company_id == SYSTEM_COMPANY_ID:
        raise HTTPException(
            status_code=400, detail="Нельзя выйти из компании system через этот endpoint"
        )

    company_repo = container.company_repository
    user_repo = container.user_repository
    target_company = await company_repo.get(target_company_id)
    if target_company is None:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    if user.user_id not in target_company.members or target_company_id not in user.companies:
        raise HTTPException(status_code=404, detail="Пользователь не состоит в выбранной компании")

    del target_company.members[user.user_id]
    del user.companies[target_company_id]

    switched_to_system = False
    if user.active_company_id == target_company_id:
        user.active_company_id = SYSTEM_COMPANY_ID
        switched_to_system = True

    await company_repo.set(target_company)
    await user_repo.set(user)

    response = JSONResponse(
        content={
            "success": True,
            "company_id": target_company_id,
            "switched_to_system": switched_to_system,
        }
    )
    if switched_to_system:
        system_roles = user.companies.get(SYSTEM_COMPANY_ID)
        if not system_roles:
            raise ValueError("У пользователя отсутствуют роли в компании system")
        token_service = get_token_service()
        refreshed_token = token_service.create_token(
            user_id=user.user_id,
            company_id=SYSTEM_COMPANY_ID,
            roles=system_roles,
            email=user.email,
        )
        settings = get_settings()
        response.set_cookie(
            key="auth_token",
            value=refreshed_token,
            domain=get_cookie_domain(request.headers.get("host", "")),
            httponly=True,
            secure=settings.server.env == "production",
            samesite="lax",
            max_age=TokenService.SESSION_EXPIRES,
        )
    return response
