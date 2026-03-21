"""
API для управления компаниями
"""
import logging
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from core.utils.subdomain import slugify, validate_slug
from core.utils.tokens import get_token_service
from core.utils.domain import get_cookie_domain, build_url
from core.models.identity_models import Company
from apps.frontend.dependencies import ContainerDep
from core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/companies", tags=["companies"])


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
    
    return CheckSlugResponse(
        available=company_id is None,
        slug=slug
    )


@router.post("", response_model=CreateCompanyResponse)
async def create_company(
    request_data: CreateCompanyRequest,
    request: Request,
    container: ContainerDep
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
    
    if not hasattr(request.state, 'user') or not request.state.user:
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
    logger.info(f"🆕 Создание компании: name={name}, slug={slug}, company_id={company_id}, owner={user.user_id}")
    
    company = Company(
        company_id=company_id,
        name=name,
        subdomain=slug,
        owner_user_id=user.user_id,
        status="active",
        members={user.user_id: ["owner"]},
    )

    await company_repo.set(company)
    logger.info(f"✅ Создана компания {company.company_id} (subdomain: {slug})")
    
    await subdomain_repo.set_mapping(slug, company.company_id)
    logger.info(f"✅ Зарегистрирован subdomain {slug} → {company.company_id}")
    
    # Проверяем что маппинг сохранился
    check_company_id = await subdomain_repo.get_company_id(slug)
    logger.info(f"🔍 Проверка маппинга: subdomain '{slug}' → company_id '{check_company_id}'")
    
    if company.company_id not in user.companies:
        user.companies[company.company_id] = ["owner"]  # Список ролей, а не строка!
        user.active_company_id = company.company_id
        await user_repo.set(user)
        logger.info(f"✅ Пользователь {user.user_id} добавлен в компанию {company.company_id} как owner")
    
    # Инициализировать агенты и тулы для новой компании
    try:
        service_client = container.service_client
        init_response = await service_client.post(
            "agents",
            "/agents/api/v1/company/init",
            json={
                "company_id": company_id,
                "company_name": name,
                "subdomain": slug
            }
        )
        
        logger.info(
            f"Инициализация агентов для {company_id} запущена: "
            f"task_id={init_response.get('task_id')}"
        )
    except Exception as e:
        logger.error(
            f"Не удалось запустить инициализацию агентов для {company_id}: {e}",
            exc_info=True
        )
        # НЕ падаем - компания уже создана
    
    redirect_url = build_url(
        request.headers.get("host", ""),
        "/dashboard",
        slug
    )
    logger.info(f"🔗 Redirect URL: {redirect_url}")
    
    # Перевыпускаем токен с company_id
    token_service = get_token_service()
    new_token = token_service.create_token(user.user_id, company.company_id)
    logger.info(f"🔑 Перевыпущен токен с company_id={company.company_id}")
    
    # Обновляем cookie
    cookie_domain = get_cookie_domain(request.headers.get("host", ""))
    is_production = settings.server.env == "production"
    
    response = JSONResponse(content={
        "company_id": company.company_id,
        "name": company.name,
        "subdomain": company.subdomain,
        "redirect_url": redirect_url
    })
    
    response.set_cookie(
        key="auth_token",
        value=new_token,
        domain=cookie_domain,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=7200
    )
    
    return response


@router.get("/me", response_model=list[dict])
async def get_my_companies(request: Request, container: ContainerDep):
    """
    Получить список компаний текущего пользователя
    
    Args:
        request: FastAPI request
        container: DI контейнер
    
    Returns:
        Список компаний с их данными
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    user = request.state.user
    company_repo = container.company_repository
    
    companies = []
    for company_id in user.companies.keys():
        company = await company_repo.get(company_id)
        if company:
            companies.append({
                "company_id": company.company_id,
                "name": company.name,
                "subdomain": company.subdomain,
                "role": user.companies[company_id],
                "is_active": company_id == user.active_company_id
            })
    
    return companies

