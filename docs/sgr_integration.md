# Интеграция SGR Deep Research

SGR (Schema-Guided Reasoning) Deep Research - микросервис для глубоких веб-исследований с использованием структурированного подхода к рассуждению.

## Архитектура

```
agent-lab (port 8001)
    ↓ HTTP
ResearchAgent → sgr_research / sgr_quick_search
    ↓ HTTP
SGR Service (port 8010)
    ↓ API
Tavily Search + OpenAI
```

## Быстрый старт

### 1. Настройка переменных окружения

Файл `.env` уже содержит необходимые переменные:

```env
SGR_OPENAI_API_KEY=your-key-here
SGR_TAVILY_API_KEY=your-key-here
```

### 2. Запуск всех сервисов

```bash
# Запуск PostgreSQL, Agent Lab, Worker и SGR
docker-compose up -d

# Проверка статуса
docker-compose ps

# Логи SGR
docker-compose logs -f sgr
```

### 3. Проверка работы

```bash
# Проверка SGR API
curl http://localhost:8010/v1/models

# Запуск тестов интеграции
uv run python test_sgr_integration.py
```

## Использование

### ResearchAgent

Agent Lab автоматически создает ResearchAgent при миграции. Агент доступен через:

- **agent_id**: `app.agents.researcher.agent.ResearchAgent`
- **Инструменты**:
  - `sgr_research` - детальное исследование (стоимость: 0.5 руб)
  - `sgr_quick_search` - быстрый поиск (стоимость: 0.1 руб)

### Пример использования

```python
from app.agents.researcher.agent import ResearchAgent, sgr_research

# Через инструмент напрямую
result = await sgr_research.ainvoke({
    "query": "Что нового в AI в 2025?",
    "detailed": True
})

# Через агента
agent = ResearchAgent(config)
response = await agent.ainvoke({
    "messages": [{"role": "user", "content": "Исследуй тренды AI"}]
})
```

### В других агентах

Добавь ResearchAgent как инструмент:

```python
class MyAgent(BaseAgent):
    name = "my_agent"
    tools = [
        "agent:app.agents.researcher.agent.ResearchAgent",
        # ... другие тулы
    ]
    prompt = """
    Для исследований используй research_agent.
    """
```

## Конфигурация

### conf.json

```json
{
  "sgr": {
    "enabled": true,
    "base_url": "http://sgr:8010",
    "timeout": 300.0,
    "openai_api_key": "...",
    "tavily_api_key": "..."
  }
}
```

### docker-compose.yml

SGR запускается автоматически при `docker-compose up`:

```yaml
sgr:
  build: ./sgr-service
  ports:
    - "8010:8010"
  environment:
    - OPENAI_API_KEY=${SGR_OPENAI_API_KEY}
    - TAVILY_API_KEY=${SGR_TAVILY_API_KEY}
```

## Биллинг

Стоимость инструментов автоматически учитывается:

- **sgr_research**: 0.5 руб за запрос
- **sgr_quick_search**: 0.1 руб за запрос

## Troubleshooting

### SGR не отвечает

```bash
# Проверка логов
docker-compose logs sgr

# Перезапуск
docker-compose restart sgr
```

### Ошибка подключения

Проверь что:
1. SGR сервис запущен: `docker-compose ps sgr`
2. Порт 8010 доступен: `curl http://localhost:8010/v1/models`
3. API ключи установлены в `.env`

### Ошибки OpenAI/Tavily

Проверь валидность ключей:
- OpenAI: https://platform.openai.com/api-keys
- Tavily: https://app.tavily.com/

## Разработка

### Локальный запуск SGR

```bash
cd sgr-service
uv sync
uv run python -m sgr_deep_research --host 127.0.0.1 --port 8010
```

### Тестирование

```bash
# Все тесты
uv run python test_sgr_integration.py

# Только HTTP клиент
uv run pytest tests/sgr/test_client.py

# Только агент
uv run pytest tests/sgr/test_agent.py
```

## Ссылки

- [SGR Deep Research GitHub](https://github.com/vamplabAI/sgr-deep-research)
- [Документация агентов](./architecture.md)
- [Биллинг система](./billing.md)

