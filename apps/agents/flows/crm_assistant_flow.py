"""
CRM Assistant Flow - AI помощник для CRM системы.

Flow для интеграции с chat widget в CRM интерфейсе.
Агент имеет доступ ко всем данным пользователя в CRM.
"""

from apps.agents.models import FlowConfig

crm_assistant_flow = FlowConfig(
    name="CRM Assistant",
    description="AI-помощник для работы с CRM: поиск информации, задачи, контакты",
    entry_point_agent="apps.agents.agents.crm.crm_assistant_agent.CRMAssistantAgent",
    
    platforms={
        "api": {},
        "web": {
            "widget_position": "bottom-right",
            "auto_open": False,
        },
        "telegram": {
            # Токен и username бота настраиваются через Variables компании
            "token": "@var:crm_telegram_bot_token",
            "username": "@var:crm_telegram_bot_username",
            # Список разрешенных telegram username (из UserProfile.telegram_username)
            "allowed_users": "@var:crm_telegram_allowed_users",
            # Флаг для маппинга telegram_username → CRM user_id
            "user_mapping": "crm_profile",
        }
    },
    
    variables={
        "assistant_name": "CRM Assistant",
        "greeting": "Привет! Я помощник CRM системы. Могу помочь найти информацию, показать задачи или рассказать о контактах. Что тебя интересует?",
        "not_found_message": "К сожалению, по твоему запросу ничего не найдено. Попробуй переформулировать.",
    },
    
    rag_config={
        "enabled": False,
    }
)

