"""
Простые админ эндпоинты для управления агентами и флоу.
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.models import AgentConfig, FlowConfig
from app.core.storage import Storage
from app.core.file_processor import FileProcessor
from app.db.database import get_db

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
        import httpx
        import re
        from bs4 import BeautifulSoup
        
        logger.info(f"Парсинг товара: {url}")
        
        if not url.startswith('http'):
            raise HTTPException(status_code=400, detail="Некорректный URL")
        
        if 'thecultt.com' not in url:
            raise HTTPException(status_code=400, detail="Поддерживаются только ссылки с thecultt.com")
        
        # Загружаем страницу
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
        
        # Парсим HTML
        soup = BeautifulSoup(html, 'html.parser')
        
        # Извлекаем изображение товара
        image_url = None
        
        # Ищем изображение товара с приоритетом на правильные селекторы
        image_selectors = [
            '.product-content-cover-list-item.active',  # Активное изображение товара
            '.product-content-cover-list-item',         # Любое изображение товара
            '.product-image img',
            '.product-gallery img',
            '.main-image img'
        ]
        
        for selector in image_selectors:
            elements = soup.select(selector)
            logger.info(f"Селектор '{selector}' нашел {len(elements)} элементов")
            
            for i, element in enumerate(elements):
                # Если это элемент с background-image в style
                if element.get('style'):
                    style = element.get('style')
                    logger.info(f"Элемент {i} style: {style[:200]}...")
                    url_match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                    if url_match:
                        found_url = url_match.group(1)
                        logger.info(f"Найден URL в style: {found_url}")
                        
                        # Проверяем, что это не логотип или SEO изображение
                        if ('storage.yandexcloud.net' in found_url and 
                            'logo' not in found_url.lower() and 
                            'seo' not in found_url.lower() and
                            found_url.endswith(('.jpg', '.jpeg', '.png', '.webp'))):
                            image_url = found_url
                            logger.info(f"✅ Принят URL: {found_url}")
                            break
                        else:
                            logger.info(f"❌ Отклонен URL: {found_url} (не подходит под критерии)")
                
                # Если это img элемент с src
                if element.name == 'img' and element.get('src'):
                    src = element.get('src')
                    logger.info(f"Найден img src: {src}")
                    
                    # Проверяем, что это изображение товара, а не логотип
                    if ('storage.yandexcloud.net' in src and 
                        'logo' not in src.lower() and 
                        'seo' not in src.lower() and
                        src.endswith(('.jpg', '.jpeg', '.png', '.webp'))):
                        image_url = src
                        logger.info(f"✅ Принят img src: {src}")
                        break
                    else:
                        logger.info(f"❌ Отклонен img src: {src} (не подходит под критерии)")
            
            if image_url:
                break
        
        # Если ничего не найдено, попробуем более общий поиск
        if not image_url:
            logger.info("Основные селекторы не сработали, пробуем общий поиск...")
            
            # Ищем все элементы с background-image
            all_elements_with_bg = soup.find_all(attrs={"style": re.compile(r"background-image")})
            logger.info(f"Найдено {len(all_elements_with_bg)} элементов с background-image")
            
            for i, element in enumerate(all_elements_with_bg):
                style = element.get('style', '')
                logger.info(f"Элемент {i}: {element.name} class='{element.get('class')}' style='{style[:150]}...'")
                
                url_match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                if url_match:
                    found_url = url_match.group(1)
                    logger.info(f"  -> URL: {found_url}")
                    
                    # Более мягкие критерии для поиска
                    if (('storage.yandexcloud.net' in found_url or 'cultt' in found_url) and 
                        'logo' not in found_url.lower() and 
                        'seo' not in found_url.lower() and
                        found_url.endswith(('.jpg', '.jpeg', '.png', '.webp'))):
                        image_url = found_url
                        logger.info(f"✅ Принят URL при общем поиске: {found_url}")
                        break
            
            # Если все еще ничего не найдено, ищем img теги
            if not image_url:
                all_imgs = soup.find_all('img')
                logger.info(f"Найдено {len(all_imgs)} img элементов")
                
                for i, img in enumerate(all_imgs[:10]):  # Ограничиваем до 10 для логов
                    src = img.get('src', '')
                    alt = img.get('alt', '')
                    logger.info(f"IMG {i}: src='{src}' alt='{alt[:50]}...'")
                    
                    if (('storage.yandexcloud.net' in src or 'cultt' in src) and 
                        'logo' not in src.lower() and 
                        'seo' not in src.lower() and
                        src.endswith(('.jpg', '.jpeg', '.png', '.webp'))):
                        image_url = src
                        logger.info(f"✅ Принят img src при общем поиске: {src}")
                        break
        
        logger.info(f"Итоговое найденное изображение: {image_url}")
        
        # Извлекаем размеры
        dimensions = {}
        property_elements = soup.select('.product-info-property')
        
        for element in property_elements:
            title_el = element.select_one('.product-info-property__title')
            value_el = element.select_one('.product-info-property__value')
            
            if title_el and value_el:
                title = title_el.get_text(strip=True)
                value = value_el.get_text(strip=True)
                
                logger.info(f"Найдено поле: '{title}' = '{value}'")
                
                try:
                    # Ищем все числа в строке
                    numbers = re.findall(r'\d+(?:\.\d+)?', value)
                    if not numbers:
                        continue
                    
                    # Берем первое число
                    numeric_value = float(numbers[0])
                    
                    title_lower = title.lower()
                    
                    # Проверяем, что это размеры самой сумки, а не ремней/ручек
                    if 'длина' in title_lower:
                        # Исключаем размеры ремней и ручек
                        if any(word in title_lower for word in ['ремн', 'ручк', 'цепочк', 'шнур']):
                            logger.info(f"🚫 Пропустили '{title}' - это размер ремня/ручки")
                            continue
                        # Длина сумки обычно 15-50 см
                        if 10 <= numeric_value <= 60:
                            dimensions['length'] = numeric_value
                            logger.info(f"✅ Сохранили длину: {numeric_value} см")
                        else:
                            logger.info(f"❌ Пропустили длину {numeric_value} см (вне диапазона 10-60)")
                    elif 'ширина' in title_lower:
                        # Исключаем размеры ремней
                        if any(word in title_lower for word in ['ремн', 'ручк', 'цепочк', 'шнур']):
                            logger.info(f"🚫 Пропустили '{title}' - это размер ремня/ручки")
                            continue
                        # Ширина сумки обычно 3-40 см
                        if 2 <= numeric_value <= 50:
                            dimensions['width'] = numeric_value
                            logger.info(f"✅ Сохранили ширину: {numeric_value} см")
                        else:
                            logger.info(f"❌ Пропустили ширину {numeric_value} см (вне диапазона 2-50)")
                    elif 'высота' in title_lower:
                        # Исключаем размеры ремней
                        if any(word in title_lower for word in ['ремн', 'ручк', 'цепочк', 'шнур']):
                            logger.info(f"🚫 Пропустили '{title}' - это размер ремня/ручки")
                            continue
                        # Высота сумки обычно 5-40 см
                        if 3 <= numeric_value <= 50:
                            dimensions['height'] = numeric_value
                            logger.info(f"✅ Сохранили высоту: {numeric_value} см")
                        else:
                            logger.info(f"❌ Пропустили высоту {numeric_value} см (вне диапазона 3-50)")
                except (AttributeError, ValueError):
                    continue
        
        # Извлекаем название товара
        title_element = soup.select_one('h1')
        title = title_element.get_text(strip=True) if title_element else "Товар"
        
        # Извлекаем ID товара из URL
        product_id_match = re.search(r'/([A-Z0-9]+)$', url)
        product_id = product_id_match.group(1) if product_id_match else None
        
        result = {
            "status": "success",
            "title": title,
            "product_id": product_id,
            "image_url": image_url,
            "dimensions": dimensions,
            "original_url": url
        }
        
        logger.info(f"Товар успешно распарсен: {title}, изображение: {bool(image_url)}")
        return result
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP ошибка при парсинге {url}: {e}")
        raise HTTPException(status_code=400, detail=f"Не удалось загрузить страницу: {str(e)}")
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
        logger.info(f"Загрузка файла: {file.filename}, размер: {file.size}, тип: {file.content_type}")
        
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
            public=True  # Делаем файл публично доступным
        )
        
        logger.info(f"Файл успешно загружен: {file_record.file_id}, URL: {file_record.url}")
        
        return {
            "status": "success",
            "file_id": file_record.file_id,
            "storage_key": file_record.key,  # s3:provider:file_id
            "url": file_record.url,
            "filename": file_record.original_name,
            "size": file_record.file_size,
            "content_type": file_record.content_type,
            "message": f"Файл {file.filename} успешно загружен"
        }
        
    except Exception as e:
        logger.error(f"Ошибка загрузки файла {file.filename}: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Ошибка загрузки файла: {str(e)}"
        )
    finally:
        if file_processor:
            await file_processor.close()
