"""
Скрипт для полной выгрузки данных из AmoCRM в CSV файлы

Выгружает все основные сущности AmoCRM в отдельные CSV файлы:
- users (пользователи)
- leads (сделки)
- contacts (контакты)
- companies (компании)
- tasks (задачи)
- customers (покупатели)
- pipelines (воронки)
- catalogs (каталоги)
- catalog_elements (элементы каталогов по каждому каталогу)
- events (события)
- talks (беседы)
- sources (источники)
- roles (роли)
- webhooks (вебхуки)
- widgets (виджеты)
- custom_fields (кастомные поля для разных сущностей)

Rate limiting: не более 7 запросов в секунду
"""

import asyncio
import csv
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from backend.app.clients.amo_crm_integration import get_amocrm_client


# ================== НАСТРОЙКИ ==================
# ВАЖНО: Замените на свои данные!
SUBDOMAIN = "vovashevakrut"
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImp0aSI6ImM1MDYwZGU5NmNmMWRhNjIxZGY3ZDk1NWE4ODBkNTZmYTM1NzBhNjI2YTk4ZjY2YTAzOGIwOWU1YzE3NTYxOGI1NDYwMWI5NDcxMWFlYWQ5In0.eyJhdWQiOiJmMzZkM2JkNC01MjE1LTRkYjgtOTAzZi01NzNkYWExNTM5ODYiLCJqdGkiOiJjNTA2MGRlOTZjZjFkYTYyMWRmN2Q5NTVhODgwZDU2ZmEzNTcwYTYyNmE5OGY2NmEwMzhiMDllNWMxNzU2MThiNTQ2MDFiOTQ3MTFhZWFkOSIsImlhdCI6MTc1OTI1Mjk3NSwibmJmIjoxNzU5MjUyOTc1LCJleHAiOjE3Njk4MTc2MDAsInN1YiI6IjEzMDUwOTI2IiwiZ3JhbnRfdHlwZSI6IiIsImFjY291bnRfaWQiOjMyNjkzODMwLCJiYXNlX2RvbWFpbiI6ImFtb2NybS5ydSIsInZlcnNpb24iOjIsInNjb3BlcyI6WyJjcm0iLCJmaWxlcyIsImZpbGVzX2RlbGV0ZSIsIm5vdGlmaWNhdGlvbnMiLCJwdXNoX25vdGlmaWNhdGlvbnMiXSwidXNlcl9mbGFncyI6MCwiaGFzaF91dWlkIjoiMTY2M2IxNGItOWUzNy00NmM3LThhNTktMDgzYzM2NGIyZjFhIiwiYXBpX2RvbWFpbiI6ImFwaS1iLmFtb2NybS5ydSJ9.f7E8JIR0mqoTLkPLhsyojR-zBXZL7HsfxwMOt99R7zvV4ZbkrXr164aFfy_tXHsIRpIexzNx6BSgpldOQZbvW9i6EA2ZyRS2sR2THeiGULhR7rwlcGDjsDuS8D2nEqTJbU8NUl8fox9VkMQfn94fVPaUINnfaOisdwRSAKDHBG5kBKYGt1x0Kcbso1Ege1qtnUEQxii51pk9pQF_5AEHRy2wARM4DfK0x9DMbsp7NS6KqWqc42fjzN9JKSjjlMeNn2tELbyhylWBis5Pj9XIBA8WT1kbcGp-FGNfK7tCsPi3csHKSO3iFQsRJDuWQJSo1nLhQoPRVJyA1rx8X_2qTQ"

# Папка для экспорта
EXPORT_DIR = Path("artifacts/amocrm_exports")

# Формат экспорта: "csv", "json" или "both"
EXPORT_FORMAT = "both"

# Rate limiting: 7 запросов в секунду = 0.143 секунды между запросами
RATE_LIMIT_DELAY = 0.143

# Размер страницы для пагинации
PAGE_SIZE = 250


# ================== RATE LIMITER ==================

class RateLimiter:
    """Ограничитель скорости запросов"""

    def __init__(self, delay: float):
        self.delay = delay
        self.last_request_time = 0

    async def wait(self):
        """Ожидает, если необходимо, чтобы соблюсти rate limit"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.delay:
            await asyncio.sleep(self.delay - time_since_last)

        self.last_request_time = time.time()


# ================== УТИЛИТЫ ==================

def flatten_dict(data: Dict[str, Any], parent_key: str = "", sep: str = "_") -> Dict[str, Any]:
    """
    Разворачивает вложенный словарь в плоский

    Пример:
        {"a": 1, "b": {"c": 2}} -> {"a": 1, "b_c": 2}
    """
    items = []
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k

        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            # Списки сохраняем как JSON строки
            items.append((new_key, json.dumps(v, ensure_ascii=False)))
        else:
            items.append((new_key, v))

    return dict(items)


def save_to_json(data: List[Dict[str, Any]], filename: str):
    """
    Сохраняет данные в JSON файл

    Args:
        data: Список словарей для сохранения
        filename: Имя файла (без расширения)
    """
    if not data:
        print(f"⚠️  {filename}: нет данных для сохранения")
        return

    # Создаем папку если её нет
    EXPORT_DIR.mkdir(exist_ok=True)

    filepath = EXPORT_DIR / f"{filename}.json"

    # Записываем JSON с отступами для читаемости
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ {filename}.json: сохранено {len(data)} записей")


def save_to_csv(data: List[Dict[str, Any]], filename: str, flatten: bool = True):
    """
    Сохраняет данные в CSV файл

    Args:
        data: Список словарей для сохранения
        filename: Имя файла (без расширения)
        flatten: Разворачивать ли вложенные структуры
    """
    if not data:
        print(f"⚠️  {filename}: нет данных для сохранения")
        return

    # Создаем папку если её нет
    EXPORT_DIR.mkdir(exist_ok=True)

    filepath = EXPORT_DIR / f"{filename}.csv"

    # Разворачиваем вложенные структуры если нужно
    if flatten:
        data = [flatten_dict(item) for item in data]

    # Собираем все уникальные ключи
    fieldnames = set()
    for item in data:
        fieldnames.update(item.keys())

    fieldnames = sorted(fieldnames)

    # Записываем CSV
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    print(f"✅ {filename}.csv: сохранено {len(data)} записей")


def save_data(data: List[Dict[str, Any]], filename: str, flatten: bool = True):
    """
    Сохраняет данные в выбранном формате (CSV, JSON или оба)

    Args:
        data: Список словарей для сохранения
        filename: Имя файла (без расширения)
        flatten: Разворачивать ли вложенные структуры (только для CSV)
    """
    if not data:
        print(f"⚠️  {filename}: нет данных для сохранения")
        return

    if EXPORT_FORMAT in ("csv", "both"):
        try:
            save_to_csv(data, filename, flatten)
        except Exception as e:
            print(f"❌ Ошибка при сохранении {filename}.csv: {e}")

    if EXPORT_FORMAT in ("json", "both"):
        try:
            save_to_json(data, filename)
        except Exception as e:
            print(f"❌ Ошибка при сохранении {filename}.json: {e}")


# ================== ФУНКЦИИ ЭКСПОРТА ==================

async def export_paginated(
    fetch_func,
    rate_limiter: RateLimiter,
    entity_name: str,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Универсальная функция для экспорта с пагинацией

    Args:
        fetch_func: Функция для получения данных (должна принимать limit и page)
        rate_limiter: Ограничитель скорости
        entity_name: Название сущности для логирования
        **kwargs: Дополнительные параметры для fetch_func
    """
    all_data = []
    page = 1

    print(f"📥 Экспорт {entity_name}...")

    while True:
        await rate_limiter.wait()

        try:
            items = await fetch_func(limit=PAGE_SIZE, page=page, **kwargs)

            if not items:
                break

            all_data.extend(items)
            print(f"   Страница {page}: получено {len(items)} записей (всего: {len(all_data)})")

            # Если получили меньше чем лимит, значит это последняя страница
            if len(items) < PAGE_SIZE:
                break

            page += 1

        except Exception as e:
            print(f"❌ Ошибка при экспорте {entity_name} на странице {page}: {e}")
            break

    return all_data


async def export_users(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт пользователей"""
    return await export_paginated(
        client.get_users,
        rate_limiter,
        "пользователей (users)",
        with_amojo_id=True,
    )


async def export_leads(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт сделок"""
    return await export_paginated(
        client.get_leads,
        rate_limiter,
        "сделок (leads)",
        with_contacts=False,
    )


async def export_contacts(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт контактов"""
    return await export_paginated(
        client.get_contacts,
        rate_limiter,
        "контактов (contacts)",
    )


async def export_companies(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт компаний"""
    return await export_paginated(
        client.get_companies,
        rate_limiter,
        "компаний (companies)",
    )


async def export_tasks(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт задач"""
    return await export_paginated(
        client.get_tasks,
        rate_limiter,
        "задач (tasks)",
    )


async def export_customers(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт покупателей"""
    return await export_paginated(
        client.get_customers,
        rate_limiter,
        "покупателей (customers)",
    )


async def export_pipelines(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт воронок со статусами"""
    print("📥 Экспорт воронок (pipelines)...")

    await rate_limiter.wait()
    pipelines = await client.get_pipelines(limit=PAGE_SIZE)

    # Для каждой воронки получаем детальную информацию со статусами
    detailed_pipelines = []
    for pipeline in pipelines:
        await rate_limiter.wait()
        detailed = await client.get_pipeline(pipeline["id"])
        detailed_pipelines.append(detailed)

    print(f"✅ Получено {len(detailed_pipelines)} воронок")
    return detailed_pipelines


async def export_catalogs(client, rate_limiter: RateLimiter) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Экспорт каталогов и их элементов

    Returns:
        Кортеж (catalogs, all_elements) где all_elements содержит элементы из всех каталогов
    """
    catalogs = await export_paginated(
        client.get_catalogs,
        rate_limiter,
        "каталогов (catalogs)",
    )

    # Экспортируем элементы каждого каталога
    all_elements = []

    for catalog in catalogs:
        catalog_id = catalog["id"]
        catalog_name = catalog.get("name", f"catalog_{catalog_id}")

        print(f"📥 Экспорт элементов каталога '{catalog_name}' (ID: {catalog_id})...")

        elements = await export_paginated(
            lambda limit, page: client.get_catalog_elements(catalog_id, limit, page),
            rate_limiter,
            f"элементов каталога '{catalog_name}'",
        )

        # Добавляем catalog_id к каждому элементу для связи
        for element in elements:
            element["catalog_id"] = catalog_id
            element["catalog_name"] = catalog_name

        all_elements.extend(elements)

    return catalogs, all_elements


async def export_events(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт событий (history)"""
    # События имеют лимит 100 на страницу
    all_data = []
    page = 1

    print("📥 Экспорт событий (events)...")

    while True:
        await rate_limiter.wait()

        try:
            items = await client.get_events(limit=100, page=page)

            if not items:
                break

            all_data.extend(items)
            print(f"   Страница {page}: получено {len(items)} записей (всего: {len(all_data)})")

            if len(items) < 100:
                break

            page += 1

        except Exception as e:
            print(f"❌ Ошибка при экспорте событий на странице {page}: {e}")
            break

    return all_data


async def export_talks(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт бесед"""
    return await export_paginated(
        client.get_talks,
        rate_limiter,
        "бесед (talks)",
    )


async def export_sources(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт источников"""
    return await export_paginated(
        client.get_sources,
        rate_limiter,
        "источников (sources)",
    )


async def export_roles(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт ролей"""
    return await export_paginated(
        client.get_roles,
        rate_limiter,
        "ролей (roles)",
    )


async def export_webhooks(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт вебхуков"""
    print("📥 Экспорт вебхуков (webhooks)...")

    await rate_limiter.wait()
    webhooks = await client.get_webhooks()

    print(f"   Получено {len(webhooks)} вебхуков")

    return webhooks


async def export_widgets(client, rate_limiter: RateLimiter) -> List[Dict[str, Any]]:
    """Экспорт виджетов"""
    print("📥 Экспорт виджетов (widgets)...")

    await rate_limiter.wait()
    widgets = await client.get_widgets()

    print(f"   Получено {len(widgets)} виджетов")

    return widgets


async def export_custom_fields(client, rate_limiter: RateLimiter) -> Dict[str, List[Dict[str, Any]]]:
    """
    Экспорт кастомных полей для разных типов сущностей

    Returns:
        Словарь {entity_type: fields}
    """
    entity_types = ["leads", "contacts", "companies", "customers", "catalogs"]
    all_fields = {}

    for entity_type in entity_types:
        print(f"📥 Экспорт кастомных полей для {entity_type}...")

        await rate_limiter.wait()

        try:
            fields = await client.get_custom_fields(entity_type, limit=PAGE_SIZE)
            all_fields[entity_type] = fields
            print(f"   Получено {len(fields)} полей для {entity_type}")
        except Exception as e:
            print(f"❌ Ошибка при экспорте полей для {entity_type}: {e}")
            all_fields[entity_type] = []

    return all_fields


async def export_account_info(client, rate_limiter: RateLimiter) -> Dict[str, Any]:
    """Экспорт информации об аккаунте"""
    print("📥 Экспорт информации об аккаунте...")

    await rate_limiter.wait()
    account = await client.get_account_info(with_amojo_id=True)

    print(f"   Получена информация об аккаунте: {account.get('name')}")

    return account


# ================== ОСНОВНАЯ ФУНКЦИЯ ==================

async def main():
    """Основная функция экспорта"""
    start_time = datetime.now()

    print("=" * 70)
    print("🚀 НАЧАЛО ЭКСПОРТА ДАННЫХ ИЗ AMOCRM")
    print("=" * 70)
    print(f"Поддомен: {SUBDOMAIN}")
    print(f"Папка экспорта: {EXPORT_DIR.absolute()}")
    print(f"Rate limit: {1/RATE_LIMIT_DELAY:.1f} запросов/сек")
    print("=" * 70)
    print()

    # Создаем клиент и rate limiter
    client = get_amocrm_client(subdomain=SUBDOMAIN, access_token=ACCESS_TOKEN)
    rate_limiter = RateLimiter(RATE_LIMIT_DELAY)

    try:
        # 1. Информация об аккаунте
        account = await export_account_info(client, rate_limiter)
        save_data([account], "account_info")

        # 2. Пользователи
        users = await export_users(client, rate_limiter)
        save_data(users, "users")

        # 3. Сделки
        leads = await export_leads(client, rate_limiter)
        save_data(leads, "leads")

        # 4. Контакты
        contacts = await export_contacts(client, rate_limiter)
        save_data(contacts, "contacts")

        # 5. Компании
        companies = await export_companies(client, rate_limiter)
        save_data(companies, "companies")

        # 6. Задачи
        tasks = await export_tasks(client, rate_limiter)
        save_data(tasks, "tasks")

        # 7. Покупатели
        customers = await export_customers(client, rate_limiter)
        save_data(customers, "customers")

        # 8. Воронки
        pipelines = await export_pipelines(client, rate_limiter)
        save_data(pipelines, "pipelines")

        # 9. Каталоги и элементы каталогов
        catalogs, catalog_elements = await export_catalogs(client, rate_limiter)
        save_data(catalogs, "catalogs")
        save_data(catalog_elements, "catalog_elements")

        # 10. События
        events = await export_events(client, rate_limiter)
        save_data(events, "events")

        # 11. Беседы
        talks = await export_talks(client, rate_limiter)
        save_data(talks, "talks")

        # 12. Источники
        sources = await export_sources(client, rate_limiter)
        save_data(sources, "sources")

        # 13. Роли
        roles = await export_roles(client, rate_limiter)
        save_data(roles, "roles")

        # 14. Вебхуки
        webhooks = await export_webhooks(client, rate_limiter)
        save_data(webhooks, "webhooks")

        # 15. Виджеты
        widgets = await export_widgets(client, rate_limiter)
        save_data(widgets, "widgets")

        # 16. Кастомные поля (по типам сущностей)
        custom_fields = await export_custom_fields(client, rate_limiter)
        for entity_type, fields in custom_fields.items():
            save_data(fields, f"custom_fields_{entity_type}")

    finally:
        await client.close()

    # Итоговая статистика
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print()
    print("=" * 70)
    print("✅ ЭКСПОРТ ЗАВЕРШЕН")
    print("=" * 70)
    print(f"Время выполнения: {duration:.1f} секунд")
    print(f"Файлы сохранены в: {EXPORT_DIR.absolute()}")
    print()

    # Список созданных файлов
    if EXPORT_DIR.exists():
        files = sorted(EXPORT_DIR.glob("*.csv"))
        print(f"Создано файлов: {len(files)}")
        for file in files:
            size_kb = file.stat().st_size / 1024
            print(f"  - {file.name} ({size_kb:.1f} KB)")

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

