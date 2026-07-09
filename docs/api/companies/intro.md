API для управления компаниями на Платформе.

## Возможности

- Создание новых компаний с уникальным субдоменом
- Проверка доступности slug для субдомена
- Получение списка компаний текущего пользователя
- Управление доступом участников компании system

## Аутентификация

Все эндпоинты требуют аутентификации через JWT токен в cookie `auth_token`.

## Примеры

### Создание компании

```bash
curl -X POST https://linnex.io/api/companies \
  -H "Content-Type: application/json" \
  -H "Cookie: auth_token=your_token" \
  -d '{
    "name": "My Company",
    "slug": "my-company"
  }'
```

!!! note "Legacy-домен"

    На `humanitec.ru` те же пути API. Подставьте `https://humanitec.ru/api/companies`, если интеграция привязана к legacy apex.

### Проверка slug

```bash
curl -X POST https://linnex.io/api/companies/check-slug \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "my-company"
  }'
```
