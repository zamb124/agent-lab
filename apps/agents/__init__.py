"""
Agents Service - сервис для управления агентами, flows и tools.

Порт: 8001
БД: agents_db (service) + shared_db

Структура:
- agents/           - Определения агентов
- tools/            - Инструменты
- flows/            - Flow конфигурации
- db/repositories/  - Репозитории (agent, flow, tool, task, session)
- services/         - Фабрики и сервисы (agent_factory, flow_factory, migration)
- api/v1/           - REST API endpoints
- workers/          - Background workers
- main.py           - FastAPI приложение
- container.py      - AgentsContainer(BaseContainer)
- config.json       - Конфигурация сервиса
"""







