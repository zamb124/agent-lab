"""
Агент с доступом к базе знаний (RAG).
Демонстрирует работу с документами и семантическим поиском.
"""

from app.agents.react_agent import ReActAgent
from app.tools.misc.standard import ask_user
from app.tools.misc.rag_tools import (
    search_knowledge_base,
    upload_document_to_knowledge_base,
    list_documents_in_knowledge_base
)


class KnowledgeBotAgent(ReActAgent):
    """Агент с доступом к базе знаний компании"""

    name = "knowledge_bot_agent"
    description = "Помощник с доступом к базе знаний и документам"

    prompt = """Ты {bot_name} - умный помощник с доступом к базе знаний компании.

У тебя есть доступ к документам компании и ты можешь:
1. Искать информацию в базе знаний
2. Загружать новые документы
3. Показывать список доступных документов

ИНСТРУМЕНТЫ:
- search_knowledge_base: поиск информации по запросу
- upload_document_to_knowledge_base: загрузка документа (если пользователь прикрепил файл)
- list_documents_in_knowledge_base: показать все документы

ВАЖНО:
- При вопросах пользователя ВСЕГДА используй search_knowledge_base
- Если информации нет в базе - честно скажи об этом
- При загрузке документа обязательно подтверди успешность
- Если пользователь спрашивает "что ты умеешь" или "какие документы" - используй list_documents_in_knowledge_base

Отвечай {greeting}"""

    tools = [
        ask_user,
        search_knowledge_base,
        upload_document_to_knowledge_base,
        list_documents_in_knowledge_base
    ]

