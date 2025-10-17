"""
Простой weather flow для демонстрации.
Использует WeatherAgent как entry point.

Демонстрирует использование переменных:
1. Хардкод значений
2. Ссылки на company variables через @var:key
3. Вложенные структуры
"""

import logging
from app.models import FlowConfig, FlowAuthor
from app.services.variables_service import VariablesService
from app.agents.weather.agent import WeatherAgent

logger = logging.getLogger(__name__)

async def install(flow_config: FlowConfig, company_id: str):
    """
    Хук установки Weather Flow.
    Создает дефолтные переменные для компании (если не созданы через UI).
    """
    variables_service = VariablesService()

    # Создаем переменные с дефолтными значениями из variables_definitions
    if hasattr(flow_config, 'variables_definitions') and flow_config.variables_definitions:
        for var_def in flow_config.variables_definitions:
            if var_def.default_value:
                # Проверяем, не создана ли уже переменная
                existing = await variables_service.get_var(var_def.key)
                if existing is None:
                    await variables_service.set_var(
                        key=var_def.key,
                        value=var_def.default_value,
                        is_secret=var_def.is_secret,
                        description=var_def.description
                    )
                    logger.info(f"Создана переменная по умолчанию: {var_def.key}")

    logger.info(f"Weather Flow установлен для компании {company_id}")
    return flow_config

async def uninstall(flow_config: FlowConfig, company_id: str):
    """
    Хук удаления Weather Flow.
    Удаляет созданные переменные.
    """
    variables_service = VariablesService()

    # Удаляем переменные из variables_definitions
    if hasattr(flow_config, 'variables_definitions') and flow_config.variables_definitions:
        for var_def in flow_config.variables_definitions:
            try:
                await variables_service.delete_var(var_def.key)
                logger.info(f"Удалена переменная: {var_def.key}")
            except Exception as e:
                logger.warning(f"Не удалось удалить переменную {var_def.key}: {e}")

    logger.info(f"Weather Flow удален из компании {company_id}")

async def after_install():
    """
    Хук выполняемый после установки flow.
    Может вернуть URL для открытия в новом окне браузера.
    
    Returns:
        str | None: URL для открытия в новом окне или None
    """
    logger.info("🎉 Weather Flow успешно установлен!")
    return "https://openweathermap.org/api"

weather_flow_config = FlowConfig(
    name="Weather Flow",
    description="Простой флоу для получения информации о погоде. При установке требуется настройка API ключа и параметров.",
    entry_point_agent=WeatherAgent,
    
    is_public=True,
    image_path="app/flows/weather_flow.jpg",
    author=FlowAuthor(
        name="Viktor Shved",
        email="viktor@shved.com",
        website="https://shved.com",
        github="https://github.com/viktorshved",
        linkedin="https://linkedin.com/in/viktorshved",
        twitter="https://twitter.com/viktorshved"
    ),
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
        # Ссылки на company variables (все настраивается при установке)
        "bot_name": "@var:bot_name",
        "greeting": "@var:greeting",
        "timeout_minutes": "@var:timeout_minutes",
        "support_email": "@var:company_support_email",
        "api_key": "@var:weather_api_key",

        # Вложенные структуры
        "settings": {
            "temperature_unit": "@var:temperature_unit",
            "language": "@var:default_language",
            "default_city": "@var:default_city"
        },

        # Списки со ссылками
        "available_cities": [
            "Москва",
            "Санкт-Петербург",
            "@var:company_city"
        ]
    },
    
    # Начальные данные store доступные в промптах через {store.max_requests} или session_get
    store={
        # Хардкод значений
        "max_requests_per_session": 10,
        "show_welcome": True,
        
        # Ссылки на company variables
        "language_preference": "@var:default_language",
        "api_key": "@var:weather_api_key",
        
        # Вложенные структуры
        "units": {
            "temperature": "celsius",
            "wind": "ms",
            "wind2": ""
        },
        
        # Смешанное использование
        "limits": {
            "max_cities": 5,
            "timeout_seconds": "@var:api_timeout",
        }
    },

    variables_definitions=[
        {
            "key": "agent_lab_whether_bot",
            "description": "Юзернейм Telegram бота для погодного ассистента",
            "default_value": "@weather_bot",
            "is_secret": False,
            "required": True
        },
        {
            "key": "agent_lab_whether_bot_telegram_bot_token",
            "description": "Токен Telegram бота для погодного ассистента",
            "is_secret": True,
            "required": True
        },
        {
            "key": "weather_api_key",
            "description": "API ключ сервиса погоды (OpenWeatherMap или аналог)",
            "is_secret": True,
            "required": True
        },
        {
            "key": "default_city",
            "description": "Город по умолчанию для прогноза погоды",
            "default_value": "Москва",
            "is_secret": False,
            "required": True
        },
        {
            "key": "company_city",
            "description": "Город компании для демонстрации погоды",
            "default_value": "Санкт-Петербург",
            "is_secret": False,
            "required": False
        },
        {
            "key": "default_language",
            "description": "Язык по умолчанию для интерфейса",
            "default_value": "ru",
            "is_secret": False,
            "required": False
        },
        {
            "key": "api_timeout",
            "description": "Таймаут для API запросов в секундах",
            "default_value": "30",
            "is_secret": False,
            "required": False
        },
        {
            "key": "bot_name",
            "description": "Имя погодного ассистента",
            "default_value": "Weather Assistant",
            "is_secret": False,
            "required": True
        },
        {
            "key": "greeting",
            "description": "Приветственное сообщение бота",
            "default_value": "Привет! Я помогу узнать погоду в любом городе.",
            "is_secret": False,
            "required": True
        },
        {
            "key": "timeout_minutes",
            "description": "Таймаут ожидания ответа в минутах",
            "default_value": "30",
            "is_secret": False,
            "required": False
        },
        {
            "key": "temperature_unit",
            "description": "Единицы измерения температуры (celsius/fahrenheit)",
            "default_value": "celsius",
            "is_secret": False,
            "required": False
        }
    ],

    install_hook=install,
    after_install_hook=after_install,
    uninstall_hook=uninstall,

)

# ═══════════════════════════════════════════════════════════════
# ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ ПЕРЕМЕННЫХ В ПРОМПТАХ
# ═══════════════════════════════════════════════════════════════
# 
# УНИФИЦИРОВАННЫЙ СИНТАКСИС (работает для ВСЕХ типов переменных):
# 
# 1. ОБЫЧНАЯ ПОДСТАНОВКА:
#    {variable}              - подставит значение или оставит {variable} если нет
#    {company_name}          → "ООО Компания"
#    {current_date}          → "2025-10-13"
# 
# 2. ОПЦИОНАЛЬНАЯ ПОДСТАНОВКА:
#    {?variable}             - подставит значение или ПУСТУЮ СТРОКУ если нет
#    {?user_email}           → "" (если email не указан)
# 
# 3. ПОДСТАНОВКА С ДЕФОЛТОМ:
#    {?variable|default}     - подставит значение или DEFAULT если нет
#    {?user_email|не указан} → "не указан"
#    {?timeout|30}           → "30"
# 
# 4. ВЛОЖЕННЫЕ ДАННЫЕ:
#    {settings.language}     - доступ к вложенным dict
#    {?store.user.name|Гость} - опциональный вложенный ключ
# 
# 5. СПЕЦИАЛЬНЫЕ ФУНКЦИИ (только для state):
#    {#messages.count}       - количество сообщений в истории
#    {#store.keys}           - список ключей в store
#    {#store.empty}          - true/false пустой ли store
#
# ═══════════════════════════════════════════════════════════════
# ПРИМЕР ПОЛНОГО ПРОМПТА:
# ═══════════════════════════════════════════════════════════════
# 
# prompt = """
# Ты {bot_name} компании {?company_name|Weather Service}.
# Дата: {current_date}, Время: {current_time}
# 
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📊 КОНТЕКСТ СЕССИИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 
# 👤 Пользователь: {?user_name|Гость}
# 💬 Запросов в диалоге: {#messages.count}
# 
# СТАТИЧЕСКИЕ НАСТРОЙКИ (из flow.variables):
# - Единицы: {settings.temperature_unit}
# - Язык: {settings.language}
# - Поддержка: {?support_email|support@company.com}
# 
# ДИНАМИЧЕСКИЕ ДАННЫЕ (из state.store):
# - Последний город: {?store.last_city|не было запросов}
# - Макс. запросов: {store.max_requests_per_session}
# - Показать приветствие: {?store.show_welcome|да}
# - Единицы температуры: {store.units.temperature}
# 
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 
# {?store.show_welcome:
#   ПЕРВЫЙ ЗАПРОС - покажи приветствие и объясни возможности.
#   После приветствия сохрани: session_set("show_welcome", false)
# }
# 
# {?store.last_city:
#   КОНТЕКСТ: Ранее пользователь интересовался {store.last_city}.
#   Можешь предложить повторить запрос для этого города.
# }
# 
# СОХРАНЕНИЕ ДАННЫХ:
# После каждого запроса погоды:
# - session_set("last_city", "название города")
# - session_set("last_temperature", "температура")
# 
# Будь дружелюбным и полезным!
# """
#
# ═══════════════════════════════════════════════════════════════
# ВАЖНЫЕ ДЕТАЛИ:
# ═══════════════════════════════════════════════════════════════
# 
# СТАТИЧЕСКИЕ ПЕРЕМЕННЫЕ (variables):
# - Резолвятся ОДИН РАЗ при компиляции графа
# - Источники: flow.variables, company_variables, системные
# - Используй для: конфигурация, константы, настройки
# 
# ДИНАМИЧЕСКИЕ ПЕРЕМЕННЫЕ (store):
# - Резолвятся ДИНАМИЧЕСКИ перед каждым вызовом LLM
# - Источник: state.store (персистится в БД)
# - Используй для: накопление данных, счетчики, флаги, история
# 
# РЕЗОЛВИНГ @var:key:
# - В flow.variables и flow.store поддерживаются ссылки @var:key
# - Автоматически резолвятся в значения из company variables при миграции
# - Пример: "api_key": "@var:openweather_api_key"
