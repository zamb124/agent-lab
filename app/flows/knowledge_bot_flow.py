"""
Пример флоу с RAG - Knowledge Bot.
Агент с доступом к базе знаний компании.

Демонстрирует:
1. Настройку RAG через flow.variables
2. Подключение RAG инструментов
3. Изоляцию данных по скоупам
"""

from app.models import FlowConfig

knowledge_bot_flow = FlowConfig(
    name="Knowledge Bot Flow",
    description="Флоу с интеграцией RAG для работы с базой знаний",
    entry_point_agent="app.agents.knowledge_bot.agent.KnowledgeBotAgent",
    
    platforms={
        "api": {},
        "telegram": {
            "username": "@var:knowledge_bot_telegram_username",
            "token": "@var:knowledge_bot_telegram_token"
        }
    },
    
    variables={
        "bot_name": "Knowledge Assistant",
        "greeting": "дружелюбно и профессионально",
        "support_email": "@var:company_support_email"
    },
    
    rag_config={
        "enabled": True,
        "namespace_scope": "company",
        "search_scopes": ["company", "flow"],
        "auto_index_messages": False
    }
)

