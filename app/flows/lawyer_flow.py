"""
Флоу для юридического агента компании ЭНЖИЛАБС.
Агент специализируется на российском законодательстве.
"""

from app.models import FlowConfig

lawyer_flow = FlowConfig(
    name="Lawyer Flow",
    description="Юридический агент для компании ЭНЖИЛАБС со специализацией на российском законодательстве",
    entry_point_agent="app.agents.lawyer.agent.LawyerAgent",
    
    image_path="app/agents/lawyer/LAWYER.png",
    
    platforms={
        "api": {},
        "telegram": {
            "username": "@var:lawyer_bot",
            "token": "@var:lawyer_bot_telegram_token"
        }
    },
    
    variables={
        "company_short_name": "ООО ЭНЖИЛАБС",
        "company_full_name": "Общество с Ограниченной Ответственностью ЭНЖИЛАБС",
        "company_short_name_en": "Angilabs LLC",
        "company_full_name_en": "Limited Liability Company Angilabs",
        "ceo_name": "Шведов Виктор Викторович",
        "bot_name": "Юридический советник ЭНЖИЛАБС"
    },
    is_public=True,
)

