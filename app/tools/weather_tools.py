"""
Мок-инструменты для работы с погодой.
"""

from ..core.tool_decorator import tool
import random


@tool(is_public=True, title="Подбор места для путешествия", cost=0.002, billing_name="travel_suggest")
async def suggest_travel(preferences: str = "") -> str:
    """
    Предложить место для путешествия.

    Args:
        preferences: Предпочтения пользователя
    """
    destinations = [
        "Париж, Франция - романтический город с Эйфелевой башней",
        "Токио, Япония - современный мегаполис с богатой культурой",
        "Барселона, Испания - архитектура Гауди и средиземноморский климат",
        "Стамбул, Турция - город на стыке Европы и Азии",
        "Рим, Италия - вечный город с древней историей",
        "Амстердам, Нидерланды - каналы и музеи",
    ]

    destination = random.choice(destinations)

    if preferences:
        return f"Учитывая предпочтения '{preferences}', рекомендую: {destination}"
    else:
        return f"Рекомендую: {destination}"


@tool(is_public=True, title="Погода в городе", cost=0.001, billing_name="weather_api")
async def get_weather(city: str) -> str:
    """
    Получить погоду в городе.

    Args:
        city: Название города
    """
    weather_conditions = ["солнечно", "облачно", "дождливо", "снежно", "туманно"]
    temperatures = list(range(-10, 35))

    condition = random.choice(weather_conditions)
    temperature = random.choice(temperatures)

    return f"Погода в {city}: {condition}, {temperature}°C"


# Список доступных инструментов для экспорта
WEATHER_TOOLS = [
    suggest_travel,
    get_weather,
]
