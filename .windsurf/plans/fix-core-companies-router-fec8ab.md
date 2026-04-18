# Исправление автоматического подключения core companies роутера

## Проблема
Я пошёл по кругу и добавил ручное подключение core_companies_router в CRM и frontend, хотя архитектура предусматривает АВТОМАТИЧЕСКОЕ подключение core роутеров через create_service_app в core/app/factory.py.

## Текущее состояние
- core/app/factory.py уже имеет автоматическое подключение core_companies_router для всех сервисов кроме frontend (строки 343-346)
- Я добавил ручное подключение в CRM main.py и frontend main.py - это дублирование
- Я изменил core/api/companies.py - убрал префикс /api/companies из роутера, что сломало путь

## План исправления

1. **Вернуть core/api/companies.py в исходное состояние**
   - Вернуть префикс `/api/companies` в роутер
   - Вернуть путь `/me` вместо `/companies/me`
   - Это нужно потому что при автоматическом подключении с префиксом `/crm/api/companies` полный путь будет `/crm/api/companies/me`

2. **Убрать ручное подключение из CRM main.py**
   - Удалить импорт `from core.api.companies import router as companies_router`
   - Удалить `app.include_router(companies_router, prefix="/crm/api", tags=["companies"])`
   - Автоматическое подключение уже есть в core/app/factory.py

3. **Проверить подключение в frontend main.py**
   - Если service_name == "frontend", автоматическое подключение НЕ работает (условие `if service_name != "frontend"`)
   - Убрать ручное подключение из routers=[companies_router]
   - Добавить ручное подключение с префиксом /api/companies после create_service_app

## Архитектура
Core роутеры автоматически подключаются в create_service_app для всех сервисов:
- core_auth_router → /{service_name}/api/auth
- core_calendar_router → /{service_name}/api/calendar  
- core_integrations_router → /{service_name}
- core_team_router → /{service_name}/api/team
- core_companies_router → /{service_name}/api/companies (кроме frontend)
- push_router → /{service_name}/api/push
- ws_router → /{service_name}/ws/notifications

Frontend - исключение, для него нужно ручное подключение core_companies_router с префиксом /api/companies.
