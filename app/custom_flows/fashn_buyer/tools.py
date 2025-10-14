"""
Инструменты для системы бота ассистента закупщика.
"""

import logging
import json
from datetime import datetime
from langchain_core.tools import tool

from app.db.repositories import Storage
from app.core.file_processor import get_default_file_processor
from app.core.context import get_context
from .models import (
    FashnIssueCard, 
    ItemPhoto, 
    Defect, 
    ItemCondition,
    IssueStatus,
    IssueComment,
    CommentRole
)

logger = logging.getLogger(__name__)


async def _generate_human_readable_id() -> str:
    """Генерирует человекочитаемый ID в формате YYYY-MM-DD-NNNN"""
    now = datetime.now()
    date_prefix = now.strftime("%Y-%m-%d")
    
    # Ищем последний номер за сегодня
    storage = Storage()
    
    # Ищем все заявки за сегодня
    all_keys = await storage.list_by_prefix("fashn_issue:", 1000)
    today_keys = [key for key in all_keys if date_prefix in key]
    
    # Извлекаем номера и находим максимальный
    max_number = 0
    for key in today_keys:
        try:
            # Формат ключа: fashn_issue:telegram_user_id:YYYY-MM-DD-NNNN
            parts = key.split(":")
            if len(parts) >= 3:
                issue_id = parts[2]
                if issue_id.startswith(date_prefix):
                    number_part = issue_id.split("-")[-1]
                    if number_part.isdigit():
                        max_number = max(max_number, int(number_part))
        except:
            continue
    
    # Следующий номер
    next_number = max_number + 1
    
    return f"{date_prefix}-{next_number:04d}"


@tool
async def save_fashn_issue_card(
    item_name: str,
    item_description: str,
    brand: str,
    photos_json: str,
    condition: str,
    defects_json: str,
    has_defects: bool,
    desired_price: float,
    currency: str = "RUB",
    additional_info: str = ""
) -> str:
    """
    Создает и сохраняет итоговую заявку товара в БД.
    
    Args:
        item_name: Название вещи
        item_description: Описание вещи
        brand: Бренд
        photos_json: JSON массив фотографий [{"file_id": "...", "description": "...", "is_main": bool}]
        condition: Состояние (excellent, good, fair, poor)
        defects_json: JSON массив дефектов [{"type": "...", "description": "...", "severity": 1-5, "location": "..."}]
        has_defects: Есть ли дефекты
        desired_price: Желаемая цена
        currency: Валюта
        additional_info: Дополнительная информация
        
    Returns:
        Информация о созданной заявке
    """
    # Получаем telegram_user_id из контекста
    context = get_context()
    telegram_user_id = context.metadata.get("telegram_user_id") or context.user.provider_user_id
    logger.info(f"🔍 save_fashn_issue_card получил telegram_user_id из контекста: {telegram_user_id}")
    
    storage = Storage()
    await get_default_file_processor()
        
    # Парсим фотографии
    logger.info(f"Парсим фотографии JSON: {photos_json}")
    photos_data = json.loads(photos_json)
    photos = []
    for photo_data in photos_data:
        photo = ItemPhoto(**photo_data)
        
        # Проверяем существование файла через Storage с контекстом компании
        file_key = f"s3:vkcloud:{photo.file_id}"
        file_data = await storage.get(file_key)
        if not file_data:
            return f"❌ Файл фотографии {photo.file_id} не найден в системе"
            
        photos.append(photo)
        
    if len(photos) < 3:
        return f"❌ Недостаточно фотографий. Нужно минимум 3, получено: {len(photos)}"
    
    # Парсим дефекты
    logger.info(f"Парсим дефекты JSON: {defects_json}")
    defects_data = json.loads(defects_json)
    defects = []
    for defect_data in defects_data:
        defect = Defect(**defect_data)
        defects.append(defect)
    
    # Создаем заявку с человекочитаемым ID
    issue_id = await _generate_human_readable_id()
    
    card = FashnIssueCard(
        issue_id=issue_id,
        telegram_user_id=telegram_user_id,
        item_name=item_name,
        item_description=item_description,
        brand=brand,
        photos=photos,
        condition=ItemCondition(condition),
        defects=defects,
        has_defects=has_defects,
        desired_price=desired_price,
        currency=currency,
        additional_info=additional_info
    )
    
    # Сохраняем заявку в БД
    await storage.set(card.storage_key, card.model_dump_json())
    
    logger.info(f"Создана заявка {card.storage_key}")
    
    # Формируем красивое резюме
    summary = f"""
✅ Заявка товара создана успешно!

📋 **Информация о товаре:**
• Вещь: {card.item_name}
• Бренд: {card.brand}
• Состояние: {card.condition.value}
• Дефекты: {"Да" if card.has_defects else "Нет"} ({len(card.defects)} шт.)
• Фотографий: {len(card.photos)}
• Цена: {card.desired_price} {card.currency}

🆔 **ID Заявки:** {card.issue_id}
📊 **Статус:** {card.status.value}
💬 **Комментариев:** {len(card.comments)}
💾 **Ключ в БД:** {card.storage_key}
"""
        
    return summary.strip()
@tool
async def get_fashn_issue_status(issue_id: str) -> str:
    """
    Получает статус заявки и все комментарии.
    
    Args:
        issue_id: ID заявки
        
    Returns:
        Подробная информация о статусе заявки и комментариях
    """
    try:
        # Получаем telegram_user_id из контекста
        context = get_context()
        if not context:
            return "❌ Нет контекста пользователя"
            
        telegram_user_id = context.metadata.get("telegram_user_id")
        if not telegram_user_id:
            telegram_user_id = context.user.provider_user_id
            
        if not telegram_user_id:
            return "❌ Не удалось получить Telegram ID пользователя"
        
        storage = Storage()
        
        # Формируем ключ для поиска заявки
        issue_key = f"fashn_issue:{telegram_user_id}:{issue_id}"
        
        # Получаем заявку из storage
        issue_data = await storage.get(issue_key)
        if not issue_data:
            return f"❌ Заявка с ID {issue_id} не найдена"
        
        # Парсим данные заявки
        issue_card = FashnIssueCard.model_validate_json(issue_data)
        
        # Формируем ответ с информацией о статусе
        status_names = {
            IssueStatus.NEW: "Новая",
            IssueStatus.NEED_INFO: "Требуется уточнение",
            IssueStatus.ON_REVIEW: "На оценке",
            IssueStatus.CONFIRMED: "Подтверждена",
            IssueStatus.CANCELED: "Отменена"
        }
        
        status_text = status_names.get(issue_card.status, issue_card.status)
        
        response_parts = [
            f"📋 **Заявка {issue_id}**",
            f"🏷️ **Товар:** {issue_card.item_name} ({issue_card.brand})",
            f"📊 **Статус:** {status_text}",
            f"💰 **Цена:** {issue_card.desired_price} {issue_card.currency}",
            f"📅 **Создана:** {issue_card.created_at[:19].replace('T', ' ')}"
        ]
        
        # Добавляем комментарии если есть
        if issue_card.comments:
            response_parts.append("")
            response_parts.append("💬 **Комментарии:**")
            
            for i, comment in enumerate(issue_card.comments, 1):
                role_name = "🔍 Ревьювер" if comment.role == CommentRole.REVIEWER else "👤 Клиент"
                comment_time = comment.created_at[:19].replace('T', ' ')
                response_parts.append(f"{i}. {role_name} ({comment_time}):")
                response_parts.append(f"   {comment.comment}")
        else:
            response_parts.append("")
            response_parts.append("💬 **Комментариев пока нет**")
        
        return "\n".join(response_parts)
        
    except Exception as e:
        logger.error(f"Ошибка получения статуса заявки {issue_id}: {e}")
        return f"❌ Ошибка получения статуса заявки: {str(e)}"


@tool  
async def add_fashn_issue_comment(issue_id: str, comment: str) -> str:
    """
    Добавляет комментарий к заявке от пользователя.
    
    Args:
        issue_id: ID заявки
        comment: Текст комментария
        
    Returns:
        Подтверждение добавления комментария
    """
    # Получаем telegram_user_id из контекста
    context = get_context()
    if not context:
        return "❌ Нет контекста пользователя"
        
    telegram_user_id = context.metadata.get("telegram_user_id")
    if not telegram_user_id:
        telegram_user_id = context.user.provider_user_id
        
    if not telegram_user_id:
        return "❌ Не удалось получить Telegram ID пользователя"
    
    storage = Storage()
    
    # Формируем ключ для поиска заявки
    issue_key = f"fashn_issue:{telegram_user_id}:{issue_id}"
    
    # Получаем заявку из storage
    issue_data = await storage.get(issue_key)
    if not issue_data:
        return f"❌ Заявка с ID {issue_id} не найдена"
    
    # Парсим данные заявки
    issue_card = FashnIssueCard.model_validate_json(issue_data)
    
    # Создаем новый комментарий
    new_comment = IssueComment(
        role=CommentRole.CLIENT,
        comment=comment
    )
    
    # Добавляем комментарий к заявке
    issue_card.comments.append(new_comment)
    
    # Сохраняем обновленную заявку
    await storage.set(issue_key, issue_card.model_dump_json())
    
    logger.info(f"✅ Добавлен комментарий к заявке {issue_id} от пользователя {telegram_user_id}")
    
    return f"✅ Комментарий добавлен к заявке {issue_id}"
