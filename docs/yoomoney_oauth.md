# Получение OAuth токена для YooMoney API

Чтобы использовать синхронизацию транзакций через API, нужен `access_token`.

## 🔑 Получение токена

### Шаг 1: Получить временный код

Перейдите по ссылке (замените `YOUR_CLIENT_ID` на ваш):

```
https://yoomoney.ru/oauth/authorize?client_id=26972EEF9554B88C491408B9537B5EBE1C1B4CF7BA1423DFB941EEEC6980D61A&response_type=code&redirect_uri=https://agents-lab.ru/auth/yoomoney/callback&scope=account-info+operation-history
```

После авторизации вы будете перенаправлены на:
```
https://agents-lab.ru/auth/yoomoney/callback?code=TEMPORARY_CODE
```

Скопируйте `code` из URL.

### Шаг 2: Обменять код на токен

```bash
curl -X POST https://yoomoney.ru/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "code=TEMPORARY_CODE&client_id=26972EEF9554B88C491408B9537B5EBE1C1B4CF7BA1423DFB941EEEC6980D61A&grant_type=authorization_code&redirect_uri=https://agents-lab.ru/auth/yoomoney/callback&client_secret=E93D898E4C1C04723FA1349C259D6FEC3CF84F6B42498BBA9B3169E7A0962052FACC445C6ECCE5C157EF8661D54F8AE9F4CAD550BD9E37772702C5766B122623"
```

Получите в ответе:
```json
{
  "access_token": "41001234567890.VERY_LONG_TOKEN_HERE"
}
```

### Шаг 3: Добавить токен в конфиг

```json
{
  "payment_providers": {
    "providers": {
      "yoomoney_main": {
        "access_token": "41001234567890.VERY_LONG_TOKEN_HERE"
      }
    }
  }
}
```

### Шаг 4: Перезапустить сервер

```bash
docker-compose restart
```

## ✅ Готово!

Теперь система будет:
1. Принимать webhook (основной способ)
2. Каждый час проверять pending транзакции через API (запасной способ)

## 🧪 Тестирование

### Ручная синхронизация:
```bash
curl -X POST http://localhost:8001/api/v1/admin/payments/sync/system \
  -H "Cookie: session_id=YOUR_SESSION"
```

### Проверка что токен работает:
```bash
curl https://yoomoney.ru/api/account-info \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Должен вернуть информацию о кошельке.

## 📊 Что синхронизируется

- Находит все транзакции со статусом `PENDING`
- Ищет их в истории операций YooMoney по `label`
- Обновляет статус на `SUCCESS` если найдены
- Пополняет баланс компании

## ⏰ Периодичность

По умолчанию синхронизация запускается **каждый час**. Можно изменить в `main.py`:

```python
payment_sync_worker = PaymentSyncWorker(sync_interval=1800)  # 30 минут
```
