"""
FAQ Flow - для ответов на общие вопросы о платформе
"""

from apps.agents.models import FlowConfig
from apps.agents.agents.faq_agent import FAQAgent

faq_flow_config = FlowConfig(
    name="FAQ - Помощник",
    description="Отвечает на вопросы о платформе Agent Lab",
    entry_point_agent=FAQAgent,
    
    platforms={
        "web": {},
        "api": {}
    },
    
    variables={
        "bot_name": "FAQ Помощник"
    },
    
    is_public=True
)

