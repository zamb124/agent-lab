# Система приема платежей

Интеграция платежных провайдеров для пополнения баланса компаний через YooMoney и другие системы.

## Архитектура

Система построена на принципах абстракции провайдеров, аналогично LLM провайдерам:

```
app/
├── core/clients/payment_providers/
│   ├── base_provider.py          # Базовый абстрактный класс
│   ├── yoomoney_provider.py      # Реализация YooMoney
│   ├── yukassa_provider.py       # Заглушка для ЮKassa
│   └── factory.py                # Фабрика провайдеров
├── models/payment_models.py      # Модели транзакций
├── services/payment_service.py   # Бизнес-логика
└── api/v1/payments.py           # API endpoints
```

## Поддерживаемые провайдеры

### YooMoney (Quickpay)

**Статус**: ✅ Полностью реализовано

**Возможности**:
- Создание платежей через Quickpay форму
- Прием HTTP-уведомлений (webhooks)
- Проверка подписи SHA1
- Автоматическое пополнение баланса

**Документация**: https://yoomoney.ru/docs/wallet

### ЮKassa

**Статус**: ⚠️ Заглушка (для будущей реализации)

**Требуется**:
- Регистрация юрлица
- API интеграция через POST /v3/payments
- IP whitelist для webhooks

## Конфигурация

### Пример conf.json

```json
{
  "payment_providers": {
    "yoomoney_main": {
      "provider_type": "yoomoney",
      "enabled": true,
      "account_number": "410011234567890",
      "notification_secret": "your_secret_here",
      "quickpay_url": "https://yoomoney.ru/quickpay/confirm.xml"
    }
  }
}
```

### Настройка YooMoney

1. **Зарегистрируйтесь** на https://yoomoney.ru
2. **Получите номер кошелька** (account_number)
3. **Настройте HTTP-уведомления**:
   - URL: `https://your-domain.com/api/v1/payments/webhook/yoomoney_main`
   - Секрет: сгенерируйте случайную строку (notification_secret)
4. **Добавьте в conf.json** параметры из шага 2-3

## Модели данных

### Transaction

```python
class Transaction(BaseModel):
    transaction_id: str           # Уникальный ID
    company_id: str              # ID компании
    user_id: str                 # Инициатор пополнения
    amount: float                # Сумма в рублях
    status: PaymentStatus        # pending/success/failed
    payment_provider: str        # yoomoney/yukassa
    external_payment_id: str     # ID в системе провайдера
    payment_url: str             # URL для оплаты
    created_at: datetime
    completed_at: datetime
```

### PaymentStatus

- `pending` - Ожидает оплаты
- `success` - Успешно оплачено
- `failed` - Ошибка оплаты
- `cancelled` - Отменено
- `refunded` - Возвращено

## API Endpoints

### POST /api/v1/payments/create

Создает транзакцию и возвращает URL для оплаты.

**Request**:
```json
{
  "amount": 1000.0,
  "provider": "yoomoney_main"  // опционально
}
```

**Response**:
```json
{
  "transaction_id": "txn_abc123",
  "payment_url": "https://yoomoney.ru/quickpay/...",
  "provider": "yoomoney_main",
  "status": "pending",
  "amount": 1000.0
}
```

### POST /api/v1/payments/webhook/{provider_name}

Принимает уведомления от платежных провайдеров.

**URL примеры**:
- `/api/v1/payments/webhook/yoomoney_main`
- `/api/v1/payments/webhook/yukassa_main`

**Обработка**:
1. Проверка подписи
2. Извлечение данных
3. Обновление транзакции
4. Пополнение баланса компании

### GET /api/v1/payments/transaction/{transaction_id}

Получить статус транзакции.

**Response**:
```json
{
  "transaction_id": "txn_abc123",
  "company_id": "comp_xyz",
  "amount": 1000.0,
  "status": "success",
  "payment_provider": "yoomoney",
  "created_at": "2025-01-01T12:00:00Z",
  "completed_at": "2025-01-01T12:05:00Z"
}
```

### GET /api/v1/payments/history

История платежей компании.

**Query params**:
- `limit` (default: 50)
- `offset` (default: 0)

### GET /api/v1/payments/providers

Список доступных провайдеров.

## Flow пользователя

```
1. Пользователь нажимает "Пополнить баланс"
   ↓
2. Открывается модальное окно с формой
   ↓
3. Вводит сумму и нажимает "Перейти к оплате"
   ↓
4. POST /api/v1/payments/create
   ↓
5. Редирект на payment_url (YooMoney)
   ↓
6. Пользователь оплачивает картой
   ↓
7. YooMoney отправляет webhook
   ↓
8. Система проверяет подпись и пополняет баланс
   ↓
9. Пользователь возвращается на success_url
```

## Безопасность

### Проверка подписи YooMoney

```python
# Формат строки для SHA1
check_string = f"{notification_type}&{operation_id}&{amount}&{currency}&{datetime}&{sender}&{codepro}&{secret}&{label}"

# Вычисление хеша
calculated_hash = hashlib.sha1(check_string.encode('utf-8')).hexdigest()

# Сравнение
if calculated_hash != received_hash:
    raise InvalidSignature()
```

### Защита от дубликатов

Все webhook сохраняются в `PaymentNotification`. Перед обработкой проверяется:
- Был ли уже обработан этот `external_payment_id`
- Если да - игнорируется

### Валидация сумм

При обработке webhook проверяется:
- Существует ли транзакция с указанным `transaction_id`
- Совпадает ли сумма в webhook с суммой в транзакции
- Не была ли транзакция уже обработана

## Добавление нового провайдера

### 1. Создайте класс провайдера

```python
# app/core/clients/payment_providers/stripe_provider.py

class StripeConfig(PaymentProviderConfig):
    provider_type: str = "stripe"
    api_key: str
    webhook_secret: str

class StripeProvider(BasePaymentProvider):
    async def create_payment(self, request: PaymentRequest) -> PaymentResponse:
        # Реализация через Stripe API
        pass
    
    async def verify_webhook(self, data: Dict) -> WebhookVerificationResult:
        # Проверка Stripe signature
        pass
```

### 2. Зарегистрируйте в фабрике

```python
# app/core/clients/payment_providers/factory.py

from .stripe_provider import StripeProvider, StripeConfig

def _create_provider(self, provider_name: str, config):
    if provider_type == "stripe":
        return StripeProvider(config)
```

### 3. Добавьте в конфигурацию

```json
{
  "payment_providers": {
    "stripe_main": {
      "provider_type": "stripe",
      "enabled": true,
      "api_key": "sk_live_...",
      "webhook_secret": "whsec_..."
    }
  }
}
```

## Настройка на продакшене

### 1. HTTPS обязателен

Все webhook URL должны использовать HTTPS для безопасности.

### 2. URL для YooMoney

Настройте в личном кабинете YooMoney:
- **HTTP-уведомления**: `https://your-domain.com/api/v1/payments/webhook/yoomoney_main`
- **Success URL**: `https://your-domain.com/billing?payment=success`
- **Fail URL**: `https://your-domain.com/billing?payment=fail`

### 3. Секретные ключи

Генерируйте сильные случайные строки для `notification_secret`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. Мониторинг

Отслеживайте логи:
- `✅ Платеж успешно обработан` - успешные пополнения
- `❌ Неверная подпись webhook` - попытки подделки
- `⚠️ Дубликат уведомления` - повторные webhook

## Настройка провайдера для компании

Каждая компания может иметь свой платежный провайдер:

```python
# В модели Company
company.payment_provider = "yoomoney_premium"  # Название из конфига
```

Если не указан - используется первый доступный провайдер.

## Тестирование

### Локальное тестирование с ngrok

```bash
# Запустите ngrok
ngrok http 8001

# URL будет вида: https://abc123.ngrok.io
# Настройте в YooMoney:
# https://abc123.ngrok.io/api/v1/payments/webhook/yoomoney_main
```

### Проверка webhook вручную

```bash
curl -X POST http://localhost:8001/api/v1/payments/webhook/yoomoney_main \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "notification_type=p2p-incoming&operation_id=123&amount=1000&..."
```

## Troubleshooting

### Webhook не приходит

1. Проверьте что URL доступен извне
2. Проверьте HTTPS
3. Посмотрите логи YooMoney в личном кабинете

### Ошибка "Invalid signature"

1. Проверьте что `notification_secret` совпадает с настройками YooMoney
2. Убедитесь что все параметры берутся в правильном порядке
3. Проверьте кодировку (должна быть UTF-8)

### Деньги не зачисляются

1. Проверьте что webhook обработался успешно (логи)
2. Проверьте статус транзакции через API
3. Убедитесь что transaction_id правильно передается в `label`

## Будущие улучшения

- [ ] ЮKassa провайдер (полная реализация)
- [ ] Stripe провайдер
- [ ] Автоматические возвраты средств
- [ ] Email уведомления о пополнении
- [ ] Webhook retry механизм
- [ ] Детальная статистика по платежам
- [ ] Экспорт истории в CSV

## См. также

- [Billing System](billing.md) - Система биллинга
- [Configuration](configuration.md) - Конфигурация приложения
- [Identity System](architecture.md#identity-system) - Компании и пользователи
