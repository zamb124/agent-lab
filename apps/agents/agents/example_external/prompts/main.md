# Cat Facts Agent

Этот flow демонстрирует интеграцию с внешним агентом по A2A протоколу.

## Архитектура

```
User -> platform (example_external flow) -> external-cat-agent -> catfact.ninja API
```

## Авторизация

Внешний агент требует API ключ в заголовке `X-API-Key`.
Ключ передается через переменную `@var:cat_agent_api_key`.

## Использование

Отправьте любое сообщение - агент вернет интересный факт о котах.

