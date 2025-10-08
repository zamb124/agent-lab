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
            "username": "@var:weather_bot_name",      # Из company variables
            "token": "@var:telegram_bot_token"        # Из company variables
        },
        
        # Вариант 3: Смешанное использование
        # "telegram": {
        #     "username": "weather_bot",              # Хардкод
        #     "token": "@var:telegram_bot_token"      # Ссылка
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
