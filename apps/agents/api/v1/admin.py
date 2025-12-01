"""
Простые админ эндпоинты для управления агентами и флоу.
"""

import httpx
import re
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from typing import List
from bs4 import BeautifulSoup
from datetime import datetime, timezone

from apps.agents.models import AgentConfig, FlowConfig
from core.models.identity_models import Company
from core.files.processors import FileProcessor
from core.context import get_context
from core.config import get_settings
from apps.agents.container import get_container, get_agents_container
from apps.agents.dependencies import (
    AgentRepositoryDep,
    FlowRepositoryDep,
    AuthServiceDep
)
from fastapi.responses import RedirectResponse
from apps.agents.services.business.telegram_poller import telegram_poller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/me")
async def get_current_user(auth_service: AuthServiceDep):
    """
    Возвращает информацию о текущем пользователе из контекста.
    Middleware уже установил контекст с авторизованным пользователем.
    """
    context = get_context()
    user = context.user
    
    email = None
    avatar_url = None
    provider_value = None
    
    all_provider_info = await auth_service.get_all_user_providers_info(user.user_id)
    if all_provider_info:
        for provider_data in all_provider_info.values():
            if provider_data.get("avatar_url") and not avatar_url:
                avatar_url = provider_data.get("avatar_url")
            if provider_data.get("email") and not email:
                email = provider_data.get("email")
    
    if context.session_id:
        session = await auth_service._get_session(context.session_id)
        if session:
            provider_value = session.provider.value
            provider_info = await auth_service.get_user_provider_info(user.user_id, session.provider)
            if provider_info:
                if provider_info.get("email"):
                    email = provider_info.get("email")
                if provider_info.get("avatar_url"):
                    avatar_url = provider_info.get("avatar_url")
    
    return {
        "user_id": user.user_id,
        "email": email,
        "name": user.name,
        "avatar_url": avatar_url,
        "provider": provider_value,
        "status": user.status.value,
    }


@router.post("/switch-company/{company_id}")
async def switch_company(company_id: str):
    """Переключить активную компанию пользователя"""
    logger.info(f"Запрос переключения компании на: {company_id}")
    
    context = get_context()
    if not context or not context.user:
        logger.error("Нет контекста или пользователя")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    user = context.user
    logger.info(f"Пользователь: {user.user_id}, текущие компании: {list(user.companies.keys())}")
    
    if company_id not in user.companies:
        logger.error(f"Пользователь {user.user_id} не имеет доступа к компании {company_id}")
        raise HTTPException(status_code=403, detail=f"У вас нет доступа к компании {company_id}")
    
    user.active_company_id = company_id
    user.updated_at = datetime.now(timezone.utc)
    
    container = get_container()
    user_repo = container.user_repository
    
    logger.info(f"Сохраняем active_company_id={company_id} для пользователя {user.user_id}")
    await user_repo.set(user)
    
    settings = get_settings()
    
    if settings.server.env == "local":
        redirect_url = f"http://{company_id}.localhost:{settings.server.port}/frontend/dashboard"
    else:
        redirect_url = f"https://{company_id}.{settings.server.domain}/frontend/dashboard"
    
    logger.info(f"✅ Переключение успешно, redirect_url: {redirect_url}")
    return {"success": True, "redirect_url": redirect_url}


@router.get("/agents", response_model=List[str])
async def list_agents(agent_repo: AgentRepositoryDep):
    """Получить список всех агентов"""
    agents = await agent_repo.list_all(limit=100)
    return [agent.agent_id for agent in agents]


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, agent_repo: AgentRepositoryDep):
    """Получить конфигурацию агента"""
    config = await agent_repo.get(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail="Agent not found")
    return config


@router.post("/agents")
async def create_agent(config: AgentConfig, agent_repo: AgentRepositoryDep):
    """Создать нового агента"""
    success = await agent_repo.set(config)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create agent")
    return {"message": "Agent created successfully", "agent_id": config.agent_id}


@router.get("/flows", response_model=List[str])
async def list_flows(flow_repo: FlowRepositoryDep):
    """Получить список всех флоу"""
    flows = await flow_repo.list_all(limit=100)
    return [flow.flow_id for flow in flows]


@router.get("/flows/{flow_id}")
async def get_flow(flow_id: str, flow_repo: FlowRepositoryDep):
    """Получить конфигурацию флоу"""
    config = await flow_repo.get(flow_id)
    if not config:
        raise HTTPException(status_code=404, detail="Flow not found")
    return config


@router.post("/flows")
async def create_flow(config: FlowConfig, flow_repo: FlowRepositoryDep):
    """Создать новый флоу"""
    success = await flow_repo.set(config)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create flow")
    return {"message": "Flow created successfully", "flow_id": config.flow_id}


@router.get("/parse-product")
async def parse_product_url(url: str):
    """
    Парсит страницу товара и извлекает информацию о продукте.
    Поддерживает thecultt.com
    """
    try:
        logger.info(f"Парсинг товара: {url}")

        if not url.startswith("http"):
            raise HTTPException(status_code=400, detail="Некорректный URL")

        if "thecultt.com" not in url:
            raise HTTPException(
                status_code=400, detail="Поддерживаются только ссылки с thecultt.com"
            )

        # Загружаем страницу
        from apps.agents.services.http_utils import get_httpx_client
        
        async with get_httpx_client(timeout=10.0) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text
            except httpx.ConnectTimeout as e:
                logger.error(f"Таймаут подключения к {url}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=408, detail=f"Таймаут подключения к сайту {url}. Сайт недоступен или медленно отвечает."
                )

        # Парсим HTML
        soup = BeautifulSoup(html, "html.parser")

        # Извлекаем все изображения товара
        image_urls = []
        main_image_url = None

        # Ищем все изображения товара с приоритетом на правильные селекторы
        image_selectors = [
            ".product-content-cover-list-item.active",  # Активное изображение товара
            ".product-content-cover-list-item",  # Любое изображение товара
            ".product-image img",
            ".product-gallery img",
            ".main-image img",
        ]

        for selector in image_selectors:
            elements = soup.select(selector)
            logger.info(f"Селектор '{selector}' нашел {len(elements)} элементов")

            for i, element in enumerate(elements):
                found_url = None
                
                # Если это элемент с background-image в style
                if element.get("style"):
                    style = element.get("style")
                    logger.info(f"Элемент {i} style: {style[:200]}...")
                    url_match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                    if url_match:
                        found_url = url_match.group(1)
                        logger.info(f"Найден URL в style: {found_url}")

                # Если это img элемент с src
                elif element.name == "img" and element.get("src"):
                    found_url = element.get("src")
                    logger.info(f"Найден img src: {found_url}")

                # Вспомогательная функция для проверки валидности изображения
                def _is_valid_product_image(url):
                    return (
                        "storage.yandexcloud.net" in url
                        and "logo" not in url.lower()
                        and "seo" not in url.lower()
                        and url.endswith((".jpg", ".jpeg", ".png", ".webp"))
                    )

                # Проверяем и добавляем URL если подходит
                if found_url and _is_valid_product_image(found_url):
                    if found_url not in image_urls:  # Избегаем дубликатов
                        image_urls.append(found_url)
                        logger.info(f"✅ Добавлен URL: {found_url}")
                        
                        # Первое найденное изображение считаем основным
                        if main_image_url is None:
                            main_image_url = found_url
                elif found_url:
                    logger.info(f"❌ Отклонен URL: {found_url} (не подходит под критерии)")

        # Если основные селекторы не дали результатов, попробуем более общий поиск
        if not image_urls:
            logger.info("Основные селекторы не сработали, пробуем общий поиск...")

            # Ищем все элементы с background-image
            all_elements_with_bg = soup.find_all(
                attrs={"style": re.compile(r"background-image")}
            )
            logger.info(
                f"Найдено {len(all_elements_with_bg)} элементов с background-image"
            )

            for i, element in enumerate(all_elements_with_bg):
                style = element.get("style", "")
                logger.info(
                    f"Элемент {i}: {element.name} class='{element.get('class')}' style='{style[:150]}...'"
                )

                url_match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                if url_match:
                    found_url = url_match.group(1)
                    logger.info(f"  -> URL: {found_url}")

                    # Более мягкие критерии для поиска
                    if (
                        ("storage.yandexcloud.net" in found_url or "cultt" in found_url)
                        and "logo" not in found_url.lower()
                        and "seo" not in found_url.lower()
                        and found_url.endswith((".jpg", ".jpeg", ".png", ".webp"))
                        and found_url not in image_urls
                    ):
                        image_urls.append(found_url)
                        if main_image_url is None:
                            main_image_url = found_url
                        logger.info(f"✅ Принят URL при общем поиске: {found_url}")

            # Если все еще мало изображений, ищем img теги
            if len(image_urls) < 3:  # Пытаемся найти больше изображений
                all_imgs = soup.find_all("img")
                logger.info(f"Найдено {len(all_imgs)} img элементов")

                for i, img in enumerate(all_imgs[:20]):  # Увеличиваем лимит для поиска больше изображений
                    src = img.get("src", "")
                    alt = img.get("alt", "")
                    logger.info(f"IMG {i}: src='{src}' alt='{alt[:50]}...'")

                    if (
                        ("storage.yandexcloud.net" in src or "cultt" in src)
                        and "logo" not in src.lower()
                        and "seo" not in src.lower()
                        and src.endswith((".jpg", ".jpeg", ".png", ".webp"))
                        and src not in image_urls
                    ):
                        image_urls.append(src)
                        if main_image_url is None:
                            main_image_url = src
                        logger.info(f"✅ Принят img src при общем поиске: {src}")

        logger.info(f"Найдено {len(image_urls)} изображений товара: {image_urls}")
        logger.info(f"Основное изображение: {main_image_url}")

        # Извлекаем размеры
        dimensions = {}
        property_elements = soup.select(".product-info-property")

        for element in property_elements:
            title_el = element.select_one(".product-info-property__title")
            value_el = element.select_one(".product-info-property__value")

            if title_el and value_el:
                title = title_el.get_text(strip=True)
                value = value_el.get_text(strip=True)

                logger.info(f"Найдено поле: '{title}' = '{value}'")

                try:
                    # Ищем все числа в строке
                    numbers = re.findall(r"\d+(?:\.\d+)?", value)
                    if not numbers:
                        continue

                    # Берем первое число
                    numeric_value = float(numbers[0])

                    title_lower = title.lower()

                    # Проверяем, что это размеры самой сумки, а не ремней/ручек
                    if "длина" in title_lower:
                        # Исключаем размеры ремней и ручек
                        if any(
                            word in title_lower
                            for word in ["ремн", "ручк", "цепочк", "шнур"]
                        ):
                            logger.info(
                                f"🚫 Пропустили '{title}' - это размер ремня/ручки"
                            )
                            continue
                        # Длина сумки обычно 15-50 см
                        if 10 <= numeric_value <= 60:
                            dimensions["length"] = numeric_value
                            logger.info(f"✅ Сохранили длину: {numeric_value} см")
                        else:
                            logger.info(
                                f"❌ Пропустили длину {numeric_value} см (вне диапазона 10-60)"
                            )
                    elif "ширина" in title_lower:
                        # Исключаем размеры ремней
                        if any(
                            word in title_lower
                            for word in ["ремн", "ручк", "цепочк", "шнур"]
                        ):
                            logger.info(
                                f"🚫 Пропустили '{title}' - это размер ремня/ручки"
                            )
                            continue
                        # Ширина сумки обычно 3-40 см
                        if 2 <= numeric_value <= 50:
                            dimensions["width"] = numeric_value
                            logger.info(f"✅ Сохранили ширину: {numeric_value} см")
                        else:
                            logger.info(
                                f"❌ Пропустили ширину {numeric_value} см (вне диапазона 2-50)"
                            )
                    elif "высота" in title_lower:
                        # Исключаем размеры ремней
                        if any(
                            word in title_lower
                            for word in ["ремн", "ручк", "цепочк", "шнур"]
                        ):
                            logger.info(
                                f"🚫 Пропустили '{title}' - это размер ремня/ручки"
                            )
                            continue
                        # Высота сумки обычно 5-40 см
                        if 3 <= numeric_value <= 50:
                            dimensions["height"] = numeric_value
                            logger.info(f"✅ Сохранили высоту: {numeric_value} см")
                        else:
                            logger.info(
                                f"❌ Пропустили высоту {numeric_value} см (вне диапазона 3-50)"
                            )
                except (AttributeError, ValueError):
                    continue

        # Извлекаем название товара
        title_element = soup.select_one("h1")
        title = title_element.get_text(strip=True) if title_element else "Товар"

        # Извлекаем ID товара из URL
        product_id_match = re.search(r"/([A-Z0-9]+)$", url)
        product_id = product_id_match.group(1) if product_id_match else None

        result = {
            "status": "success",
            "title": title,
            "product_id": product_id,
            "image_url": main_image_url,  # Основное изображение для обратной совместимости
            "image_urls": image_urls,     # Все найденные изображения
            "dimensions": dimensions,
            "original_url": url,
        }

        logger.info(f"Товар успешно распарсен: {title}, изображений: {len(image_urls)}")
        return result

    except httpx.ConnectTimeout as e:
        logger.error(f"Таймаут подключения при парсинге {url}: {e}", exc_info=True)
        raise HTTPException(
            status_code=408, detail=f"Таймаут подключения к {url}. Проверьте доступность сайта или настройки прокси."
        )
    except httpx.HTTPError as e:
        logger.error(f"HTTP ошибка при парсинге {url}: {e}", exc_info=True)
        error_detail = str(e) if str(e) else f"{type(e).__name__}: {getattr(e, 'message', 'Неизвестная ошибка HTTP')}"
        raise HTTPException(
            status_code=400, detail=f"Не удалось загрузить страницу: {error_detail}"
        )
    except Exception as e:
        logger.error(f"Ошибка парсинга товара {url}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка парсинга: {str(e)}")


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Загрузка файла в платформу.
    Возвращает file_id для дальнейшего использования в системе.
    """
    file_processor = None
    try:
        logger.info(
            f"Загрузка файла: {file.filename}, размер: {file.size}, тип: {file.content_type}"
        )

        # Читаем содержимое файла
        file_content = await file.read()

        # Инициализируем FileProcessor
        from apps.agents.container import get_agents_container
        storage = get_agents_container().storage
        file_processor = FileProcessor(storage=storage)

        # Обрабатываем файл (загружаем в S3 и сохраняем метаданные)
        file_record = await file_processor.process_file_from_bytes(
            data=file_content,
            original_name=file.filename or "uploaded_file",
            content_type=file.content_type or "application/octet-stream",
            uploaded_by="admin_api",
            public=True,  # Делаем файл публично доступным
        )

        logger.info(
            f"Файл успешно загружен: {file_record.file_id}, URL: {file_record.url}"
        )

        return {
            "status": "success",
            "file_id": file_record.file_id,
            "storage_key": file_record.key,  # s3:provider:file_id
            "url": file_record.url,
            "filename": file_record.original_name,
            "size": file_record.file_size,
            "content_type": file_record.content_type,
            "message": f"Файл {file.filename} успешно загружен",
        }

    except Exception as e:
        logger.error(f"Ошибка загрузки файла {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки файла: {str(e)}")
    finally:
        if file_processor:
            await file_processor.close()


# === Создание компании текущим пользователем ===

@router.post("/create-my-company")
async def create_my_company(request: Request):
    """Создать компанию для текущего авторизованного пользователя"""
    
    form_data = await request.form()
    company_data = dict(form_data)
    
    logger.info(f"DEBUG: form_data = {company_data}")
    
    context = get_context()
    if not context or not context.user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    user = context.user
    
    logger.info(f"DEBUG: user.companies = {user.companies}")
    logger.info(f"DEBUG: user.active_company_id = '{user.active_company_id}'")
    
    company_name = company_data.get("name", f"Компания {user.name}")
    slug = company_data.get("slug")
    if not slug:
        raise HTTPException(status_code=400, detail="Slug компании обязателен")
    
    container = get_agents_container()
    subdomain_repo = container.subdomain_repository
    company_repo = container.company_repository
    user_repo = container.user_repository
    
    existing = await subdomain_repo.get_company_id(slug)
    if existing:
        raise HTTPException(status_code=400, detail=f"Slug {slug} уже занят")
    
    company_id = slug
    subdomain = slug
    
    company = Company(
        company_id=company_id,
        subdomain=subdomain,
        name=company_name,
        status="active",
        created_at=datetime.now(timezone.utc)
    )
    
    await company_repo.set(company)
    await subdomain_repo.set_mapping(subdomain, company_id)
    logger.info(f"DEBUG: subdomain:{subdomain} -> {company_id} сохранен")
    
    migrator = get_container().migrator
    logger.info(f"Начинаем миграцию базовых сущностей для компании {company_id}...")
    await migrator.migrate_defaults_for_company(company)
    logger.info(f"Базовые сущности успешно мигрированы для компании {company_id}")
    
    user.companies[company_id] = ["admin", "user"]
    user.active_company_id = company_id
    user.updated_at = datetime.now(timezone.utc)
    
    await user_repo.set(user)
    logger.info(f"DEBUG: Обновлен глобальный пользователь - добавлена компания {company_id}")
    
    # Редиректим на dashboard поддомена компании
    settings = get_settings()
    if settings.server.env == "local":
        # Для local добавляем порт frontend сервиса
        company_url = f"http://{subdomain}.localhost:8002/frontend/dashboard"
    else:
        company_url = f"https://{subdomain}.{settings.server.domain}/frontend/dashboard"
    return RedirectResponse(url=company_url, status_code=302)


@router.post("/remigrate/{entity_type}/{entity_id:path}")
async def remigrate_entity(entity_type: str, entity_id: str):
    """
    Перемигрирует сущность из кода для отката к базовому состоянию.

    Args:
        entity_type: Тип сущности (flow, agent, tool)
        entity_id: ID сущности (например, apps.agents.flows.test_flow.test_flow_config)
    """
    context = get_context()
    if not context or not context.active_company:
        raise HTTPException(status_code=401, detail="Unauthorized")

    migrator = get_agents_container().migrator
    company = context.active_company
    
    if entity_type == "flow":
        await migrator.remigrate_flow(entity_id, company)
        return {"status": "success", "message": f"Flow {entity_id} успешно перемигрирован"}
    elif entity_type == "agent":
        await migrator.remigrate_agent(entity_id, company)
        return {"status": "success", "message": f"Агент {entity_id} успешно перемигрирован"}
    elif entity_type == "tool":
        await migrator.remigrate_tool(entity_id, company)
        return {"status": "success", "message": f"Tool {entity_id} успешно перемигрирован"}
    else:
        raise HTTPException(status_code=400, detail=f"Неизвестный тип сущности: {entity_type}")


@router.post("/remigrate-flow-with-deps/{flow_id:path}")
async def remigrate_flow_with_dependencies(flow_id: str):
    """
    Перемигрирует flow со всеми зависимостями.
    Полный сброс flow к базовому состоянию.
    
    Args:
        flow_id: ID flow (например, apps.agents.flows.test_flow.test_flow_config)
    """
    context = get_context()
    if not context or not context.active_company:
        raise HTTPException(status_code=401, detail="Unauthorized")

    migrator = get_agents_container().migrator
    company = context.active_company

    await migrator.migrate_for_company(
        company=company,
        flows=[flow_id],
        with_dependencies=True
    )
    
    return {"status": "success", "message": f"Flow {flow_id} и все зависимости успешно перемигрированы"}


@router.post("/remigrate-all-public/{company_id}")
async def remigrate_all_public_for_company(company_id: str):
    """
    Перемигрирует все публичные (is_public=True) flows, агенты и тулы для компании.
    Используется для обновления компании до актуального состояния из кода.
    
    Args:
        company_id: ID компании для перемиграции
    """
    context = get_context()
    if not context or not context.user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    if "system" not in context.user.companies or "admin" not in context.user.companies["system"]:
        raise HTTPException(status_code=403, detail="Access denied. System admin required.")
    
    container = get_container()
    company_repo = container.company_repository
    
    company = await company_repo.get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    migrator = get_container().migrator
    await migrator.migrate_defaults_for_company(company)
    
    return {
        "status": "success",
        "message": f"Все публичные сущности успешно перемигрированы для компании {company.name}"
    }


@router.post("/reload-telegram-bots")
async def reload_telegram_bots():
    """
    Перезагружает список Telegram ботов в long polling режиме.
    Используется после добавления новых платформ.
    Работает только в локальном окружении (ENV=local).
    """
    settings = get_settings()
    if settings.server.env != "local":
        raise HTTPException(
            status_code=400,
            detail="Telegram polling доступен только в локальном окружении"
        )
    
    try:
        await telegram_poller.reload()
        return {
            "status": "success",
            "message": f"Telegram polling перезагружен. Активных ботов: {len(telegram_poller.active_bots)}",
            "bots": list(telegram_poller.active_bots.keys())
        }
    except Exception as e:
        logger.error(f"Ошибка перезагрузки telegram polling: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка перезагрузки: {str(e)}")


@router.get("/llm/providers")
async def get_llm_providers():
    """Получить список доступных LLM моделей через OpenRouter (legacy endpoint)"""
    return await get_llm_models()


@router.get("/llm/models")
async def get_llm_models():
    """Получить список доступных LLM моделей через OpenRouter"""
    settings = get_settings()
    
    if not hasattr(settings.llm, 'openrouter') or not settings.llm.openrouter.enabled:
        return {
            "default_model": settings.llm.default_model,
            "models": []
        }
    
    models_list = []
    for model_id, model_config in settings.llm.models.items():
        input_cost_per_1m = model_config.input_cost_per_token * 1_000_000
        output_cost_per_1m = model_config.output_cost_per_token * 1_000_000
        
        cost_display = f" (вход: {input_cost_per_1m:.2f}₽, выход: {output_cost_per_1m:.2f}₽ за 1М токенов)"
        
        label = f"{model_id}"
        if model_config.description:
            label += f" - {model_config.description}"
        label += cost_display
        
        models_list.append({
            "value": model_id,
            "label": label,
            "input_cost_per_1m": round(input_cost_per_1m, 2),
            "output_cost_per_1m": round(output_cost_per_1m, 2)
        })
    
    return {
        "default_model": settings.llm.default_model,
        "models": models_list
    }


@router.get("/platforms/config")
async def get_platforms_config():
    """Получить конфигурацию поддерживаемых платформ"""
    return {
        "platforms": {
            "telegram": {
                "name": "Telegram",
                "icon": "bi-telegram",
                "fields": [
                    {
                        "name": "token",
                        "type": "password",
                        "label": "Bot Token",
                        "placeholder": "Токен от @BotFather",
                        "required": True
                    },
                    {
                        "name": "username",
                        "type": "text",
                        "label": "Username",
                        "placeholder": "username бота (без @)",
                        "required": True
                    }
                ]
            },
            "whatsapp": {
                "name": "WhatsApp",
                "icon": "bi-whatsapp",
                "fields": [
                    {
                        "name": "phone_number_id",
                        "type": "text",
                        "label": "Phone Number ID",
                        "placeholder": "111111111111111",
                        "required": True
                    },
                    {
                        "name": "access_token",
                        "type": "password",
                        "label": "Access Token",
                        "placeholder": "EAAxxxx...",
                        "required": True
                    },
                    {
                        "name": "verify_token",
                        "type": "password",
                        "label": "Verify Token",
                        "placeholder": "Ваш verify token",
                        "required": True
                    },
                    {
                        "name": "business_account_id",
                        "type": "text",
                        "label": "Business Account ID",
                        "placeholder": "123456789",
                        "required": False
                    }
                ]
            },
            "amocrm": {
                "name": "AmoCRM",
                "icon": "bi-building",
                "fields": [
                    {
                        "name": "token",
                        "type": "password",
                        "label": "API Key",
                        "placeholder": "API ключ AmoCRM",
                        "required": True
                    },
                    {
                        "name": "username",
                        "type": "text",
                        "label": "Subdomain",
                        "placeholder": "Домен (example.amocrm.ru)",
                        "required": True
                    }
                ]
            },
            "web": {
                "name": "Web",
                "icon": "bi-globe",
                "fields": [
                    {
                        "name": "username",
                        "type": "text",
                        "label": "Chat Name",
                        "placeholder": "Название чата",
                        "required": True
                    }
                ]
            },
            "api": {
                "name": "API",
                "icon": "bi-code-slash",
                "fields": [
                    {
                        "name": "token",
                        "type": "password",
                        "label": "API Key",
                        "placeholder": "API ключ (опционально)",
                        "required": False
                    },
                    {
                        "name": "username",
                        "type": "text",
                        "label": "API Name",
                        "placeholder": "Название API",
                        "required": True
                    }
                ]
            }
        }
    }
