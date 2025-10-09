"""
Простые админ эндпоинты для управления агентами и флоу.
"""

import httpx
import re
import logging
import uuid
from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from datetime import datetime, timezone

from app.models import AgentConfig, FlowConfig
from app.identity.models import User, Company
from app.core.storage import Storage
from app.core.file_processor import FileProcessor
from app.core.context import get_context
from app.core.migrator import Migrator
from app.core.config import get_settings
logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/agents", response_model=List[str])
async def list_agents():
    """Получить список всех агентов"""
    storage = Storage()
    keys = await storage.list_by_prefix("agent:", limit=100)
    return [key.replace("agent:", "") for key in keys]


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Получить конфигурацию агента"""
    storage = Storage()
    config = await storage.get_agent_config(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail="Agent not found")
    return config


@router.post("/agents")
async def create_agent(config: AgentConfig):
    """Создать нового агента"""
    storage = Storage()
    success = await storage.set_agent_config(config)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create agent")
    return {"message": "Agent created successfully", "agent_id": config.agent_id}


@router.get("/flows", response_model=List[str])
async def list_flows():
    """Получить список всех флоу"""
    storage = Storage()
    keys = await storage.list_by_prefix("flow:", limit=100)
    return [key.replace("flow:", "") for key in keys]


@router.get("/flows/{flow_id}")
async def get_flow(flow_id: str):
    """Получить конфигурацию флоу"""
    storage = Storage()
    config = await storage.get_flow_config(flow_id)
    if not config:
        raise HTTPException(status_code=404, detail="Flow not found")
    return config


@router.post("/flows")
async def create_flow(config: FlowConfig):
    """Создать новый флоу"""
    storage = Storage()
    success = await storage.set_flow_config(config)
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
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text

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

        # Вспомогательная функция для проверки валидности изображения
        def _is_valid_product_image(url):
            return (
                "storage.yandexcloud.net" in url
                and "logo" not in url.lower()
                and "seo" not in url.lower()
                and url.endswith((".jpg", ".jpeg", ".png", ".webp"))
            )

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

    except httpx.HTTPError as e:
        logger.error(f"HTTP ошибка при парсинге {url}: {e}")
        raise HTTPException(
            status_code=400, detail=f"Не удалось загрузить страницу: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Ошибка парсинга товара {url}: {e}")
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
        file_processor = FileProcessor()

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
    
    # Получаем данные из формы
    form_data = await request.form()
    company_data = dict(form_data)
    
    # Отладка: что пришло из формы
    logger.info(f"🐛 DEBUG: form_data = {company_data}")
    
    context = get_context()
    if not context or not context.user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    user = context.user
    storage = Storage()
    
    # Отладка: проверим что в контексте
    logger.info(f"🐛 DEBUG: user.companies = {user.companies}")
    logger.info(f"🐛 DEBUG: user.active_company_id = '{user.active_company_id}'")
    
    # Пользователь может создавать несколько компаний
    
    # Создаем компанию
    company_name = company_data.get("name", f"Компания {user.name}")
    slug = company_data.get("slug")
    if not slug:
        raise HTTPException(status_code=400, detail="Slug компании обязателен")
    
    # Проверяем уникальность slug
    existing_subdomain = await storage.get(f"subdomain:{slug}", force_global=True)
    if existing_subdomain:
        raise HTTPException(status_code=400, detail=f"Slug {slug} уже занят")
    
    # ID компании = slug (то что указал пользователь)
    company_id = slug
    subdomain = slug  # Для совместимости
    
    company = Company(
        company_id=company_id,
        subdomain=subdomain,
        name=company_name,
        status="active",
        created_at=datetime.now(timezone.utc)
    )
    
    # Сохраняем компанию глобально
    await storage.set(f"company:{company_id}", company.model_dump_json(), force_global=True)
    
    # Сохраняем mapping поддомена (как JSON строка)
    subdomain_saved = await storage.set(f"subdomain:{subdomain}", f'"{company_id}"', force_global=True)
    logger.info(f"🐛 DEBUG: subdomain:{subdomain} -> {company_id}, saved: {subdomain_saved}")
    
    # Мигрируем базовые сущности для новой компании
    migrator = Migrator()
    logger.info(f"Начинаем миграцию базовых сущностей для компании {company_id}...")
    await migrator.migrate_defaults_for_company(company)
    logger.info(f"✅ Базовые сущности успешно мигрированы для компании {company_id}")
    
    # Обновляем глобального пользователя - добавляем компанию
    user_key = f"user:{user.user_id}"
    user.companies[company_id] = ["admin", "user"]
    user.active_company_id = company_id
    user.updated_at = datetime.now(timezone.utc)
    
    await storage.set(user_key, user.model_dump_json(), force_global=True)
    logger.info(f"🐛 DEBUG: Обновлен глобальный пользователь - добавлена компания {company_id}")
    
    # Редиректим на dashboard
    from fastapi.responses import RedirectResponse
    from app.core.config import settings
    
    # Для локальной разработки редиректим на localhost без поддомена
    if settings.server.env == "local":
        return RedirectResponse(url="/frontend/dashboard", status_code=302)
    else:
        # Для продакшена используем поддомен
        company_url = f"http://{subdomain}.{settings.server.domain}/frontend/dashboard"
        return RedirectResponse(url=company_url, status_code=302)


@router.post("/remigrate/{entity_type}/{entity_id:path}")
async def remigrate_entity(entity_type: str, entity_id: str):
    """
    Перемигрирует сущность из кода для отката к базовому состоянию.
    
    Args:
        entity_type: Тип сущности (flow, agent, tool)
        entity_id: ID сущности (например, app.flows.test_flow.test_flow_config)
    """
    context = get_context()
    if not context or not context.active_company:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    migrator = Migrator()
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
        flow_id: ID flow (например, app.flows.test_flow.test_flow_config)
    """
    context = get_context()
    if not context or not context.active_company:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    migrator = Migrator()
    company = context.active_company
    
    await migrator.migrate_for_company(
        company=company,
        flows=[flow_id],
        with_dependencies=True
    )
    
    return {"status": "success", "message": f"Flow {flow_id} и все зависимости успешно перемигрированы"}


@router.post("/reload-telegram-bots")
async def reload_telegram_bots():
    """
    Перезагружает список Telegram ботов в long polling режиме.
    Используется после добавления новых платформ.
    Работает только в локальном окружении (ENV=local).
    """
    from app.core.config import settings
    
    if settings.server.env != "local":
        raise HTTPException(
            status_code=400,
            detail="Telegram polling доступен только в локальном окружении"
        )
    
    try:
        from app.services.telegram_poller import telegram_poller
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
    """Получить список доступных LLM провайдеров и их моделей"""
    settings = get_settings()
    
    providers_data = {}
    for provider_name, provider_config in settings.llm.providers.items():
        if not provider_config.enabled:
            continue
            
        providers_data[provider_name] = {
            "name": provider_name,
            "default_model": provider_config.default_model,
            "models": []
        }
    
    # Добавляем модели для каждого провайдера
    model_definitions = {
        "openai": [
            {"value": "", "label": "По умолчанию"},
            {"value": "gpt-4", "label": "GPT-4"},
            {"value": "gpt-4-turbo", "label": "GPT-4 Turbo"},
            {"value": "gpt-3.5-turbo", "label": "GPT-3.5 Turbo"},
            {"value": "gpt-4o", "label": "GPT-4o"},
            {"value": "gpt-4o-mini", "label": "GPT-4o Mini"},
        ],
        "gemini": [
            {"value": "", "label": "По умолчанию"},
            {"value": "gemini-1.5-pro", "label": "Gemini 1.5 Pro"},
            {"value": "gemini-1.5-flash", "label": "Gemini 1.5 Flash"},
            {"value": "gemini-pro", "label": "Gemini Pro"},
        ],
        "yandex": [
            {"value": "", "label": "По умолчанию"},
            {"value": "yandexgpt/latest", "label": "YandexGPT Latest"},
            {"value": "yandexgpt-lite/latest", "label": "YandexGPT Lite"},
        ],
        "anthropic": [
            {"value": "", "label": "По умолчанию"},
            {"value": "claude-3-opus-20240229", "label": "Claude 3 Opus"},
            {"value": "claude-3-sonnet-20240229", "label": "Claude 3 Sonnet"},
            {"value": "claude-3-haiku-20240307", "label": "Claude 3 Haiku"},
        ]
    }
    
    for provider_name in providers_data:
        if provider_name in model_definitions:
            providers_data[provider_name]["models"] = model_definitions[provider_name]
        else:
            providers_data[provider_name]["models"] = [{"value": "", "label": "По умолчанию"}]
    
    return {
        "default_provider": settings.llm.default_provider,
        "providers": providers_data
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
