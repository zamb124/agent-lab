"""
API для экспорта данных CRM в различные форматы.
"""

import io
from datetime import date

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse

from apps.crm.dependencies import NoteServiceDep, EntityServiceDep, TaskServiceDep

router = APIRouter()


def generate_pdf_from_html(html_content: str) -> bytes:
    """
    Генерирует PDF из HTML.
    Использует weasyprint если доступен, иначе возвращает HTML как fallback.
    """
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content).write_pdf()
        return pdf_bytes
    except ImportError:
        # Fallback: возвращаем HTML если weasyprint не установлен
        return html_content.encode('utf-8')


def create_note_html(note: dict, entities: list = None) -> str:
    """Создает HTML для заметки"""
    entities_html = ""
    if entities:
        entities_html = "<h3>Связанные сущности</h3><ul>"
        for entity in entities:
            entities_html += f"<li><strong>{entity.get('name', 'N/A')}</strong> ({entity.get('type', 'N/A')})</li>"
        entities_html += "</ul>"
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{note.get('title', 'Заметка')}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 40px;
                color: #333;
                line-height: 1.6;
            }}
            h1 {{ color: #2D3A4F; margin-bottom: 8px; }}
            .meta {{ color: #666; font-size: 14px; margin-bottom: 24px; }}
            .content {{ white-space: pre-wrap; }}
            .summary {{ background: #f5f5f5; padding: 16px; border-radius: 8px; margin-top: 24px; }}
            h3 {{ color: #5B8EC2; margin-top: 32px; }}
            ul {{ padding-left: 20px; }}
            li {{ margin: 8px 0; }}
        </style>
    </head>
    <body>
        <h1>{note.get('title', 'Без названия')}</h1>
        <div class="meta">
            Дата: {note.get('note_date', 'N/A')} | 
            Тип: {note.get('note_type', 'freeform')}
        </div>
        <div class="content">{note.get('content', '')}</div>
        {f'<div class="summary"><strong>AI Резюме:</strong><br>{note.get("ai_summary")}</div>' if note.get('ai_summary') else ''}
        {entities_html}
    </body>
    </html>
    """


def create_entity_html(entity: dict, relationships: list = None, notes: list = None) -> str:
    """Создает HTML для сущности"""
    relationships_html = ""
    if relationships:
        relationships_html = "<h3>Связи</h3><ul>"
        for rel in relationships:
            relationships_html += f"<li>{rel.get('relationship_type', 'N/A')}: {rel.get('target_entity_id', 'N/A')}</li>"
        relationships_html += "</ul>"
    
    notes_html = ""
    if notes:
        notes_html = "<h3>Связанные заметки</h3><ul>"
        for note in notes[:10]:  # Ограничиваем 10 заметками
            notes_html += f"<li><strong>{note.get('title', 'N/A')}</strong> ({note.get('note_date', 'N/A')})</li>"
        notes_html += "</ul>"
    
    attributes_html = ""
    if entity.get('attributes'):
        attributes_html = "<h3>Атрибуты</h3><table>"
        for key, value in entity.get('attributes', {}).items():
            attributes_html += f"<tr><td><strong>{key}:</strong></td><td>{value}</td></tr>"
        attributes_html += "</table>"
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{entity.get('name', 'Сущность')}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 40px;
                color: #333;
                line-height: 1.6;
            }}
            h1 {{ color: #2D3A4F; margin-bottom: 8px; }}
            .meta {{ color: #666; font-size: 14px; margin-bottom: 24px; }}
            h3 {{ color: #5B8EC2; margin-top: 32px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            td {{ padding: 8px; border-bottom: 1px solid #eee; }}
            ul {{ padding-left: 20px; }}
            li {{ margin: 8px 0; }}
        </style>
    </head>
    <body>
        <h1>{entity.get('name', 'Без названия')}</h1>
        <div class="meta">
            Тип: {entity.get('type', 'N/A')} | 
            Статус: {entity.get('status', 'N/A')}
        </div>
        {attributes_html}
        {relationships_html}
        {notes_html}
    </body>
    </html>
    """


@router.get("/note/{note_id}")
async def export_note(
    note_id: str,
    note_service: NoteServiceDep,
    entity_service: EntityServiceDep,
    format: str = Query("pdf", description="Формат: pdf или html"),
):
    """
    Экспортирует заметку в PDF или HTML.
    """
    note = await note_service.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    
    # Получаем связанные сущности
    entities = []
    if note.linked_entity_ids:
        for entity_id in note.linked_entity_ids:
            entity = await entity_service.get_entity(entity_id)
            if entity:
                entities.append(entity.model_dump())
    
    html_content = create_note_html(note.model_dump(), entities)
    
    if format == "html":
        return StreamingResponse(
            io.BytesIO(html_content.encode('utf-8')),
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="note_{note_id}.html"'}
        )
    
    pdf_bytes = generate_pdf_from_html(html_content)
    media_type = "application/pdf" if isinstance(pdf_bytes, bytes) and pdf_bytes[:4] == b'%PDF' else "text/html"
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="note_{note_id}.pdf"'}
    )


@router.get("/entity/{entity_id}")
async def export_entity(
    entity_id: str,
    entity_service: EntityServiceDep,
    note_service: NoteServiceDep,
    format: str = Query("pdf", description="Формат: pdf или html"),
):
    """
    Экспортирует сущность в PDF или HTML.
    """
    entity = await entity_service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Сущность не найдена")
    
    # Получаем связанные заметки
    notes = await note_service.get_notes_by_entity(entity_id)
    
    html_content = create_entity_html(
        entity.model_dump(),
        relationships=[],  # TODO: добавить
        notes=[n.model_dump() for n in notes] if notes else []
    )
    
    if format == "html":
        return StreamingResponse(
            io.BytesIO(html_content.encode('utf-8')),
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="entity_{entity_id}.html"'}
        )
    
    pdf_bytes = generate_pdf_from_html(html_content)
    media_type = "application/pdf" if isinstance(pdf_bytes, bytes) and pdf_bytes[:4] == b'%PDF' else "text/html"
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="entity_{entity_id}.pdf"'}
    )


@router.get("/daily-report/{report_date}")
async def export_daily_report(
    report_date: date,
    note_service: NoteServiceDep,
    task_service: TaskServiceDep,
    format: str = Query("pdf", description="Формат: pdf или html"),
):
    """
    Экспортирует дневной отчет с заметками и задачами.
    """
    notes = await note_service.filter_notes(
        start_date=report_date,
        end_date=report_date
    )
    tasks = await task_service.get_due_today()
    
    notes_html = ""
    for note in notes:
        notes_html += f"""
        <div class="note">
            <h3>{note.title}</h3>
            <div class="note-content">{note.content}</div>
            {f'<div class="summary">{note.ai_summary}</div>' if note.ai_summary else ''}
        </div>
        """
    
    tasks_html = ""
    for task in tasks:
        status_icon = "✓" if task.status == "completed" else "○"
        tasks_html += f"<li>{status_icon} <strong>{task.title}</strong> - {task.status}</li>"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Отчет за {report_date}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 40px;
                color: #333;
                line-height: 1.6;
            }}
            h1 {{ color: #2D3A4F; }}
            h2 {{ color: #5B8EC2; margin-top: 32px; border-bottom: 2px solid #5B8EC2; padding-bottom: 8px; }}
            .note {{ margin: 24px 0; padding: 16px; background: #f9f9f9; border-radius: 8px; }}
            .note h3 {{ margin-top: 0; color: #333; }}
            .summary {{ background: #e8f4fd; padding: 12px; border-radius: 4px; margin-top: 12px; }}
            ul {{ list-style: none; padding: 0; }}
            li {{ padding: 8px 0; border-bottom: 1px solid #eee; }}
        </style>
    </head>
    <body>
        <h1>Отчет за {report_date}</h1>
        
        <h2>Заметки ({len(notes)})</h2>
        {notes_html if notes_html else '<p>Нет заметок за этот день</p>'}
        
        <h2>Задачи ({len(tasks)})</h2>
        <ul>{tasks_html if tasks_html else '<li>Нет задач</li>'}</ul>
    </body>
    </html>
    """
    
    if format == "html":
        return StreamingResponse(
            io.BytesIO(html_content.encode('utf-8')),
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="report_{report_date}.html"'}
        )
    
    pdf_bytes = generate_pdf_from_html(html_content)
    media_type = "application/pdf" if isinstance(pdf_bytes, bytes) and pdf_bytes[:4] == b'%PDF' else "text/html"
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="report_{report_date}.pdf"'}
    )

