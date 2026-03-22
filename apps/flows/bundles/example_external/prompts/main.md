# Cat Facts (внешний flow)

Этот flow демонстрирует интеграцию с внешним сервисом по A2A.

## Архитектура

```
User -> platform (example_external flow) -> external-cat-endpoint -> catfact.ninja API
```

## Авторизация

Внешний endpoint требует API ключ в заголовке `X-API-Key`.
Ключ передается через переменную `@var:cat_flow_api_key`.

## Использование

Отправьте любое сообщение — вернётся интересный факт о котах.
