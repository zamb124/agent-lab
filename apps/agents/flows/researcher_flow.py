"""
Research Flow - flow для глубоких веб-исследований через SGR Deep Research.
"""

from apps.agents.models import FlowConfig

researcher_flow_config = FlowConfig(
    name="Research Flow",
    description="Flow для глубоких веб-исследований с помощью SGR Deep Research",
    entry_point_agent="apps.agents.agents.researcher.agent.ResearchAgent",
    
    platforms={
        "api": {},
        "telegram": {
            "username": "@var:researcher_bot_username",
            "token": "@var:researcher_bot_telegram_token"
        },
        "web": {}
    },
    
    variables={
        "bot_name": "Research Assistant",
        "greeting": "Привет! Я помогу найти актуальную информацию в интернете.",
        "timeout_minutes": "180"
    },
    
    is_public=True,
)

