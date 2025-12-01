"""
Apps - сервисы платформы Humanitec.

Структура:
- agents/   - Сервис агентов (порт 8001)
- frontend/ - Сервис фронтенда (порт 8002)

Каждый сервис:
- Наследуется от core.container.BaseContainer
- Имеет свою БД + shared БД
- Имеет свой config.json
- Имеет свой main.py с FastAPI app
"""

