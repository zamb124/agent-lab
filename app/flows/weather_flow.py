"""
Простой weather flow для демонстрации.
Использует WeatherAgent как entry point.

Демонстрирует использование переменных:
1. Хардкод значений
2. Ссылки на company variables через @var:key
3. Вложенные структуры
"""

from app.models import FlowConfig

weather_flow_config = FlowConfig(
    name="Weather Flow",
    description="Простой флоу для получения информации о погоде",
    entry_point_agent="app.agents.weather.agent.WeatherAgent",
    
    # Пример platforms с разными вариантами
    platforms={
        "api": {},
        
        # Вариант 1: Хардкод токена (не рекомендуется для production)
        # "telegram": {
        #     "username": "weather_bot",
        #     "token": "123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        # },
        
        # Вариант 2: Ссылка на переменную компании (рекомендуется)
        "telegram": {
            "username": "@var:agent_lab_whether_bot",
            "token": "@var:agent_lab_whether_bot_telegram_bot_token"
        },
        
        # Вариант 3: Смешанное использование
        # "telegram": {
        #     "username": "weather_bot",
        #     "token": "@var:telegram_bot_token"
        # },
        
        # WhatsApp - все креды через переменные (рекомендуется)
        "whatsapp": {
            "phone_number_id": "@var:whether_bot_whatsapp_phone_number_id",
            "access_token": "@var:whether_bot_whatsapp_access_token",
            "verify_token": "@var:whether_bot_whatsapp_verify_token",
            "business_account_id": "@var:whether_bot_whatsapp_business_account_id",
            "display_name": "Weather Assistant",
            "graph_api_version": "v18.0",
            "graph_api_url": "https://graph.facebook.com"
        },
        
        # WhatsApp (альтернативный вариант с хардкодом - НЕ рекомендуется)
        # "whatsapp": {
        #     "phone_number_id": "111111111111111",
        #     "access_token": "EAAxxxx...",
        #     "verify_token": "my_secret_verify_token_123",
        #     "business_account_id": "123456789",
        #     "display_name": "Weather Assistant"
        # }
    },
    
    # Переменные flow доступные в промптах агентов через {bot_name}, {timeout_minutes}
    variables={
        # Хардкод значений
        "bot_name": "Weather Assistant",
        "greeting": "Привет! Я помогу узнать погоду в любом городе.",
        "timeout_minutes": "30",
        
        # Ссылки на company variables
        "support_email": "@var:company_support_email",
        "api_key": "@var:weather_api_key",
        
        # Вложенные структуры
        "settings": {
            "temperature_unit": "celsius",
            "language": "ru",
            "default_city": "@var:default_city"  # Ссылка внутри dict
        },
        
        # Списки со ссылками
        "available_cities": [
            "Москва",
            "Санкт-Петербург",
            "@var:company_city"  # Ссылка внутри list
        ]
    }
)

# Для использования переменных в промптах агента:
# 
# AgentConfig.prompt = """
# Ты {bot_name}.
# {greeting}
# 
# Настройки:
# - Единицы: {settings[temperature_unit]}
# - Язык: {settings[language]}
# - Город по умолчанию: {settings[default_city]}
# 
# При проблемах: {support_email}
# """
#
# В runtime все @var:key автоматически резолвятся в значения из company variables.
