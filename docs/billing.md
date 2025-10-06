# Система биллинга Agent Lab

Система учета стоимости использования ресурсов на уровне компаний.

## Принципы работы

**Основная идея**: Компания имеет баланс, каждый вызов LLM/tool списывает средства с баланса.

**Тарифные планы** влияют на стоимость через множители к базовой цене:
- **FREE** - полная цена (множитель 1.0)
- **BASIC** - скидка 20-30% (множитель 0.7-0.8)
- **PREMIUM** - скидка 50-70% (множитель 0.3-0.5)  
- **ENTERPRISE** - бесплатно (множитель 0.0)

## Компоненты системы

### Company (Компания)

Каждая компания имеет:

```python
class Company:
    company_id: str              # ID компании
    tariff_plan: TariffPlan      # Тарифный план
    balance: float               # Текущий баланс в рублях
    monthly_budget: float        # Месячный лимит расходов (опционально)
    current_month_spent: float   # Потрачено в текущем месяце
    billing_period_start: datetime  # Начало периода
```

### BillingService

Основной сервис для работы с биллингом:

**Файл**: `app/services/billing_service.py`

**Методы**:
- `can_use_resource()` - проверяет достаточно ли средств
- `record_usage()` - записывает использование и списывает с баланса
- `get_resource_cost_for_company()` - рассчитывает стоимость для компании
- `get_company_usage_stats()` - статистика использования
- `reset_monthly_billing()` - сброс месячных счетчиков

### UsageRecord

Запись об использовании ресурса:

```python
class UsageRecord:
    usage_id: str
    user_id: str
    company_id: str
    session_id: Optional[str]
    usage_type: UsageType  # TOOL_CALL, LLM_REQUEST, etc
    resource_name: str     # "openai:gpt-4", "tool:weather_api"
    cost: float           # Списанная сумма в рублях
    quantity: int         # Количество (токены, вызовы)
    metadata: Dict
    timestamp: datetime
```

Хранятся с ключом: `usage:{company_id}:{resource_name}:{usage_id}`

## Тарифные планы

Определены в `app/models/billing_models.py`:

```python
TARIFF_PRICES = {
    TariffPlan.FREE: {
        "openai": {},      # Базовая цена
        "gemini": {},
        "tools": {},
    },
    TariffPlan.BASIC: {
        "openai": {
            "gpt-4": 0.8,        # Скидка 20%
            "gpt-3.5-turbo": 0.8,
        },
        "gemini": {"*": 0.8},  # Для всех моделей
        "tools": {"*": 0.7},    # Скидка 30%
    },
    TariffPlan.PREMIUM: {
        "openai": {"*": 0.5},   # Скидка 50%
        "gemini": {"*": 0.5},
        "tools": {"*": 0.3},    # Скидка 70%
    },
    TariffPlan.ENTERPRISE: {
        "openai": {"*": 0.0},   # Бесплатно
        "gemini": {"*": 0.0},
        "tools": {"*": 0.0},
    }
}
```

## Базовые цены ресурсов

Определены в `BillingService._get_base_resource_cost()`:

### LLM (за запрос)

```python
llm_base_prices = {
    "openai": {
        "gpt-4": 1.0,
        "gpt-4o": 0.8,
        "gpt-3.5-turbo": 0.1,
    },
    "gemini": {
        "gemini-2.0-flash-exp": 0.2,
        "gemini-2.5-pro": 0.5,
        "gemini-1.5-flash": 0.15,
    },
    "yandex": {
        "yandexgpt/latest": 0.3,
    },
    "anthropic": {
        "claude-3-sonnet": 0.7,
    }
}
```

### Инструменты (за вызов)

```python
tool_base_prices = {
    "weather_api": 0.1,
    "travel_suggest": 0.2,
    "calculator": 0.0,         # Бесплатно
    "nano_banana_generation": 0.5,
    "fashn_buyer_agent": 0.0,  # Бесплатно
}
```

## Формат resource_name

Все ресурсы именуются по формату `category:resource`:

- LLM: `openai:gpt-4`, `gemini:gemini-2.0-flash-exp`
- Tools: `tool:weather_api`, `tool:calculator`

## Расчет итоговой стоимости

```
Итоговая стоимость = Базовая цена × Тарифный множитель
```

**Примеры**:

1. FREE план, OpenAI GPT-4:
   - Базовая: 1.0₽
   - Множитель: 1.0 (нет скидки)
   - Итого: 1.0₽

2. BASIC план, OpenAI GPT-4:
   - Базовая: 1.0₽
   - Множитель: 0.8 (скидка 20%)
   - Итого: 0.8₽

3. PREMIUM план, tool:weather_api:
   - Базовая: 0.1₽
   - Множитель: 0.3 (скидка 70%)
   - Итого: 0.03₽

4. ENTERPRISE план, любой ресурс:
   - Базовая: любая
   - Множитель: 0.0
   - Итого: 0₽ (бесплатно)

## Создание инструментов с биллингом

### Декоратор @tool

```python
from app.core.tool_decorator import tool

@tool(cost=0.1, billing_name="weather_api")
def get_weather(city: str) -> str:
    """Получить погоду"""
    return f"Погода в {city}: солнечно"

@tool  # Бесплатный инструмент (cost=0.0 по умолчанию)
def calculate(expression: str) -> str:
    """Калькулятор"""
    return f"Результат: {eval(expression)}"
```

**Параметры декоратора**:
- `cost` - базовая стоимость в рублях (по умолчанию 0.0)
- `billing_name` - название для биллинга (по умолчанию имя функции)
- `free_for_plans` - не используется в текущей версии
- `required_permissions` - для будущего расширения
- `max_calls_per_hour` - для будущего расширения

**Важно**: Декоратор только добавляет метаданные к функции. Реальный биллинг происходит при вызове через ToolFactory.

## LLM биллинг

LLM автоматически оборачиваются в `ChatOpenAIWithBilling` при создании:

```python
# Создание LLM (автоматически с биллингом)
llm = get_llm("openai", "gpt-4")

# При вызове:
result = await llm.ainvoke("Привет!")
# Автоматически:
# 1. Проверяется баланс компании через can_use_resource()
# 2. Выполняется запрос
# 3. Списываются средства через record_usage()
```

**Файл**: `app/core/llm_billing_wrapper.py`

## Проверки перед использованием

Метод `BillingService.can_use_resource()` проверяет:

1. **Баланс компании** - достаточно ли средств
   ```python
   if company.balance < resource_cost:
       return False, "Недостаточно средств"
   ```

2. **Месячный бюджет** (если установлен)
   ```python
   if company.monthly_budget > 0:
       if company.current_month_spent + resource_cost > company.monthly_budget:
           return False, "Превышен месячный лимит"
   ```

## Управление компанией

### Создание компании

```python
from app.identity.models import Company

company = Company(
    company_id="my_company",
    subdomain="mycompany",
    name="My Company",
    tariff_plan="premium",
    balance=10000.0,          # 10,000₽ начальный баланс
    monthly_budget=5000.0,    # Лимит 5,000₽/месяц (опционально)
    current_month_spent=0.0
)

# Сохранить в БД
storage = Storage()
await storage.set(f"company:{company.company_id}", company.model_dump_json(), force_global=True)
```

### Пополнение баланса

```python
# Получить компанию
company_data = await storage.get("company:my_company", force_global=True)
company = Company.model_validate_json(company_data)

# Пополнить баланс
company.balance += 1000.0

# Сохранить
await storage.set(f"company:{company.company_id}", company.model_dump_json(), force_global=True)
```

### Смена тарифа

```python
company.tariff_plan = "enterprise"
await storage.set(f"company:{company.company_id}", company.model_dump_json(), force_global=True)
```

## Статистика использования

```python
from app.services.billing_service import BillingService

billing_service = BillingService()
stats = await billing_service.get_company_usage_stats("company_id")

# Результат:
{
    "total_cost": 1250.50,      # Общая стоимость за месяц
    "total_calls": 15420,       # Общее количество вызовов
    "by_resource": {
        "openai:gpt-4": {
            "cost": 900.0,
            "calls": 300
        },
        "tool:weather_api": {
            "cost": 350.5,
            "calls": 15120
        }
    },
    "by_user": {
        "user_123": {
            "cost": 800.0,
            "calls": 8000
        }
    }
}
```

## Обработка ошибок

### TariffError

Выбрасывается когда ресурс недоступен для тарифа:

```python
from app.exceptions import TariffError

try:
    result = await llm.ainvoke("test")
except TariffError as e:
    # Предложить повысить тариф
    print(f"Доступ запрещен: {e}")
```

### BillingError

Выбрасывается при проблемах с балансом или бюджетом:

```python
from app.exceptions import BillingError

try:
    result = await tool.ainvoke(...)
except BillingError as e:
    # Предложить пополнить баланс
    print(f"Ошибка биллинга: {e}")
```

## Миграция

При запуске приложения `Migrator` сканирует все функции с декоратором `@tool` и сохраняет метаданные в БД.

**Файл**: `app/core/migrator.py`

```python
# Автоматически при старте
migrator = Migrator()
await migrator.run_full_migration()
```

## Настройка базовых цен

Чтобы изменить базовые цены, отредактируйте:

`app/services/billing_service.py` → `_get_base_resource_cost()`

```python
llm_base_prices = {
    "openai": {
        "gpt-4": 2.0,  # Изменить базовую цену
    }
}
```

## Настройка тарифных множителей

`app/models/billing_models.py` → `TARIFF_PRICES`

```python
TARIFF_PRICES = {
    TariffPlan.BASIC: {
        "openai": {
            "gpt-4": 0.9,  # Меньшая скидка (10% вместо 20%)
        }
    }
}
```

## Сброс месячного биллинга

В начале каждого месяца нужно сбрасывать счетчик `current_month_spent`:

```python
await billing_service.reset_monthly_billing("company_id")
```

Это нужно делать через cron или планировщик задач.

## Тестирование

```bash
# Все тесты биллинга
uv run pytest tests/billing/ -v

# Конкретный тест
uv run pytest tests/billing/test_billing_service.py::test_can_use_resource -v
```

**Тесты**:
- `tests/billing/test_billing_service.py` - тесты BillingService
- `tests/billing/test_simple_billing.py` - тесты моделей
- `tests/billing/test_tool_billing.py` - тесты биллинга инструментов
- `tests/billing/test_tariff_prices.py` - тесты тарифных множителей

## Примеры использования

### Проверка доступа к ресурсу

```python
billing_service = BillingService()

can_use, reason = await billing_service.can_use_resource(
    user=current_user,
    company=current_company,
    resource_name="openai:gpt-4"
)

if not can_use:
    print(f"Доступ запрещен: {reason}")
```

### Запись использования вручную

```python
await billing_service.record_usage(
    user=current_user,
    company=current_company,
    resource_name="tool:custom_api",
    cost=0.5,
    usage_type=UsageType.TOOL_CALL,
    quantity=1,
    metadata={"custom_field": "value"}
)
```

## Архитектурные особенности

1. **Контекст** - биллинг использует глобальный контекст для определения текущей компании
2. **Storage** - все записи хранятся в единой таблице с префиксами
3. **Составные ключи** - `usage:{company_id}:{resource_name}:{usage_id}` для эффективного поиска
4. **force_global=True** - биллинговые данные не привязаны к компаниям через префикс контекста

## Будущие улучшения

- Интеграция с платежными системами
- API для управления балансом
- Веб-интерфейс мониторинга
- Алерты при низком балансе
- Экспорт отчетов в CSV/Excel
- Поддержка нескольких валют
- Система скидок и промокодов

## См. также

- [Архитектура](architecture.md) - общая архитектура платформы
- [Identity System](architecture.md#identity-system) - пользователи и компании
- [Configuration](configuration.md) - настройка LLM с ценами