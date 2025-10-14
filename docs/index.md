# Добро пожаловать в Agent Lab

**Agent Lab** - современная платформа для создания умных ИИ-агентов на базе LangGraph. Автоматизируйте общение с клиентами, создавайте мультиагентные системы и интегрируйте с любыми сервисами.

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Быстрый старт**

    ---

    Создайте первого бота за 5 минут

    [:octicons-arrow-right-24: Начало работы](user_docs/getting_started.md)

-   :material-api:{ .lg .middle } **API Reference**

    ---

    Полная документация API для разработчиков

    [:octicons-arrow-right-24: API документация](api.md)

-   :material-cube-outline:{ .lg .middle } **Архитектура**

    ---

    Изучите внутреннее устройство платформы

    [:octicons-arrow-right-24: Архитектура](architecture.md)

-   :material-puzzle:{ .lg .middle } **Интеграции**

    ---

    Подключайте Telegram, WhatsApp, AmoCRM и другие сервисы

    [:octicons-arrow-right-24: Интеграции](integrations/amocrm/README.md)

</div>

## Начните за минуты

=== "Python"

    ```python
    from app.agents.base import BaseAgent
    from langchain_core.tools import tool

    @tool
    async def get_weather(city: str) -> str:
        """Получить погоду в городе"""
        return f"Погода в {city}: солнечно, +20°C"

    class WeatherAgent(BaseAgent):
        name = "weather_agent"
        prompt = "Ты помощник по погоде. Используй инструменты для ответа."
        tools = [get_weather]
    ```

=== "API"

    ```bash
    curl -X POST http://localhost:8001/api/v1/agents \
      -H "Content-Type: application/json" \
      -d '{
        "name": "weather_agent",
        "prompt": "Ты помощник по погоде",
        "tools": ["get_weather"]
      }'
    ```

=== "UI"

    1. Откройте веб-интерфейс на `http://localhost:8001`
    2. Перейдите в раздел "Боты"
    3. Нажмите "Создать бота"
    4. Выберите платформу и настройте агента
    5. Готово!

!!! tip "Совет"
    Используйте готовые агенты из библиотеки или создайте своего с нуля. Все агенты работают одинаково независимо от способа создания.

---

## Возможности платформы

<div class="grid cards" markdown>

-   :material-brain:{ .lg .middle } **Мультиагентные системы**

    ---

    Создавайте сложные системы из нескольких специализированных агентов на базе LangGraph

-   :material-api:{ .lg .middle } **Гибкая интеграция**

    ---

    Подключайте любые API, внешние сервисы и инструменты через унифицированный интерфейс

-   :material-message-text:{ .lg .middle } **Мультиплатформность**

    ---

    Telegram, WhatsApp, Web, AmoCRM - один агент работает везде

-   :material-chart-line:{ .lg .middle } **Аналитика и биллинг**

    ---

    Отслеживайте использование, стоимость запросов и производительность агентов

-   :material-database:{ .lg .middle } **RAG и база знаний**

    ---

    Интегрируйте собственную базу знаний для точных и релевантных ответов

-   :material-lock:{ .lg .middle } **Безопасность**

    ---

    Мультитенантность, аутентификация через OAuth, контроль доступа

</div>

## Популярные сценарии

!!! example "FAQ Bot"
    Автоматические ответы на типовые вопросы клиентов с поддержкой базы знаний
    
    ```python
    class FAQAgent(BaseAgent):
        name = "faq_agent"
        prompt = "Отвечай на вопросы клиентов, используя базу знаний"
        tools = [search_knowledge_base, escalate_to_human]
    ```

!!! example "Sales Assistant"
    Умный консультант для увеличения продаж и персонализированных рекомендаций
    
    - Анализ предпочтений клиента
    - Рекомендации товаров
    - Интеграция с каталогом и CRM

!!! example "Complaint Handler"
    Обработка жалоб с автоматическим созданием тикетов и маршрутизацией
    
    - Классификация жалоб
    - Сбор деталей инцидента
    - Создание тикетов в CRM
    - Эскалация к ответственным

---

## Полезные ссылки

**Для пользователей:**
- [Начало работы](user_docs/getting_started.md) - первый бот за 5 минут
- [Управление ботами](user_docs/bots_management.md) - создание и настройка
- [Платформы](user_docs/platforms.md) - Telegram, WhatsApp, Web, AmoCRM, API
- [Возможности](user_docs/features.md) - файлы, речь, виртуальная примерка, RAG

**Для разработчиков:**
- [API документация](api.md) - интеграция и разработка
- [Архитектура](architecture.md) - как устроена система
- [LLM и OpenRouter](llm.md) - настройка языковых моделей
- [Интеграции](integrations/amocrm/README.md) - подключение внешних сервисов  

