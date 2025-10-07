"""
Скрипт для экспорта сделок из AmoCRM с историей чата

Выгружает:
- Все сделки с их основными данными
- Историю событий (timeline) по каждой сделке, включая сообщения чата
- Сохраняет результат в JSON файл
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

from app.clients.amo_crm_integration.client import get_amocrm_client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_all_leads(
    client,
    limit_per_page: int = 250,
    with_contacts: bool = True,
) -> List[Dict[str, Any]]:
    """
    Получает все сделки с пагинацией

    Args:
        client: AmoCRM клиент
        limit_per_page: Количество сделок на странице (макс 250)
        with_contacts: Включить связанные контакты

    Returns:
        Список всех сделок
    """
    all_leads = []
    page = 1

    logger.info("Начинаем загрузку сделок...")

    while True:
        try:
            leads = await client.get_leads(
                limit=limit_per_page,
                page=page,
                with_contacts=with_contacts
            )

            if not leads:
                logger.info(f"Загрузка завершена. Всего получено сделок: {len(all_leads)}")
                break

            all_leads.extend(leads)
            logger.info(f"Страница {page}: получено {len(leads)} сделок (всего: {len(all_leads)})")
            page += 1

        except Exception as e:
            logger.error(f"Ошибка при получении сделок на странице {page}", exc_info=True)
            break

    return all_leads


async def get_lead_timeline(
    client,
    lead_id: int,
    created_at_from: float = None,
    created_at_to: float = None,
) -> Dict[str, Any]:
    """
    Получает историю событий сделки включая сообщения чата

    Args:
        client: AmoCRM клиент
        lead_id: ID сделки
        created_at_from: Начальная дата (timestamp)
        created_at_to: Конечная дата (timestamp)

    Returns:
        История событий сделки или пустой dict при ошибке
    """
    try:
        timeline = await client.get_lead_events_timeline(
            lead_id=lead_id,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
        )
        logger.info(f"✅ Получена история для сделки {lead_id}")
        return timeline
    except Exception as e:
        logger.warning(f"⚠️ Не удалось получить историю для сделки {lead_id}: {e}")
        return {}


async def export_leads_with_chat_history(
    subdomain: str = None,
    access_token: str = None,
    output_file: str = None,
    created_at_from: float = None,
    created_at_to: float = None,
) -> None:
    """
    Экспортирует все сделки с историей чата

    Args:
        subdomain: Поддомен AmoCRM
        access_token: Токен доступа
        output_file: Путь к файлу для сохранения результата
        created_at_from: Фильтр по дате создания (timestamp от)
        created_at_to: Фильтр по дате создания (timestamp до)
    """
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"amocrm_export_{timestamp}.json"

    logger.info("=" * 80)
    logger.info("Начинаем экспорт данных из AmoCRM")
    logger.info("=" * 80)

    client = get_amocrm_client(subdomain=subdomain, access_token=access_token)

    try:
        account_info = await client.get_account_info()
        logger.info(f"Подключен к аккаунту: {account_info.get('name', 'N/A')}")
        logger.info(f"ID аккаунта: {account_info.get('id', 'N/A')}")

        all_leads = await get_all_leads(client, with_contacts=True)
        logger.info(f"\n📊 Загружено {len(all_leads)} сделок")

        export_data = {
            "export_date": datetime.now().isoformat(),
            "account_info": account_info,
            "total_leads": len(all_leads),
            "leads": []
        }

        logger.info("\n" + "=" * 80)
        logger.info("Начинаем загрузку истории чатов для каждой сделки...")
        logger.info("=" * 80 + "\n")

        for idx, lead in enumerate(all_leads, 1):
            lead_id = lead.get("id")
            lead_name = lead.get("name", "Без названия")

            logger.info(f"[{idx}/{len(all_leads)}] Обрабатываем сделку: {lead_name} (ID: {lead_id})")

            timeline = await get_lead_timeline(
                client,
                lead_id=lead_id,
                created_at_from=created_at_from,
                created_at_to=created_at_to,
            )

            lead_data = {
                "lead_info": lead,
                "timeline": timeline,
            }

            export_data["leads"].append(lead_data)

            await asyncio.sleep(0.1)

        logger.info("\n" + "=" * 80)
        logger.info("Сохраняем результаты в файл...")
        logger.info("=" * 80)

        output_path = Path(output_file)
        output_path.write_text(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

        logger.info(f"\n✅ Экспорт успешно завершен!")
        logger.info(f"📁 Результаты сохранены в: {output_path.absolute()}")
        logger.info(f"📊 Экспортировано сделок: {len(all_leads)}")
        logger.info(f"💾 Размер файла: {output_path.stat().st_size / 1024 / 1024:.2f} МБ")

    except Exception as e:
        logger.error(f"❌ Ошибка при экспорте данных", exc_info=True)
        raise

    finally:
        await client.close()
        logger.info("🔌 Соединение с AmoCRM закрыто")


async def main():
    """
    Основная функция запуска экспорта

    Настройте subdomain и access_token перед запуском:
    - subdomain: поддомен вашего аккаунта AmoCRM
    - access_token: OAuth 2.0 токен доступа
    """

    # НАСТРОЙКИ - укажите ваши данные
    SUBDOMAIN = None  # или "your-subdomain"
    ACCESS_TOKEN = None  # или "your-access-token"

    # Если в конфиге есть настройки AmoCRM, они будут использованы автоматически
    # Иначе раскомментируйте и укажите вручную:
    # from app.clients.amo_crm_integration.client import register_subdomain
    # register_subdomain(SUBDOMAIN, ACCESS_TOKEN)

    # Опционально: фильтр по датам (timestamp)
    # import time
    # week_ago = time.time() - (7 * 24 * 60 * 60)
    # created_at_from = week_ago

    await export_leads_with_chat_history(
        subdomain=SUBDOMAIN,
        access_token=ACCESS_TOKEN,
        output_file="amocrm_leads_export.json",
        # created_at_from=created_at_from,  # раскомментируйте для фильтра по дате
    )


if __name__ == "__main__":
    asyncio.run(main())

