# 💰 Система биллинга и тарификации Agent Lab

Полная система биллинга и контроля доступа на уровне компаний с поддержкой тарифных планов, лимитов использования и учета стоимости.

## 🏗️ Архитектура

### Основные принципы
- **Тарифы на уровне компаний** - каждая компания имеет свой тарифный план
- **Автоматический биллинг** - все LLM запросы и инструменты автоматически тарифицируются
- **Гибкие лимиты** - количественные лимиты + бюджетные ограничения
- **Переопределение в БД** - параметры из кода можно изменить через UI

### Компоненты системы
- **BillingService** - основная логика биллинга и проверки лимитов
- **ToolReference** - модель инструмента с биллинг параметрами
- **Company** - модель компании с тарифным планом и бюджетом
- **UsageRecord** - записи об использовании ресурсов
- **@tool декоратор** - расширенный декоратор с поддержкой биллинга

## 🎯 Тарифные планы

### Доступные планы
```python
class TariffPlan(str, Enum):
    FREE = "free"           # Бесплатный
    BASIC = "basic"         # Базовый  
    PREMIUM = "premium"     # Премиум
    ENTERPRISE = "enterprise" # Корпоративный
```

### Лимиты по тарифам (глобальные)
```python
# app/models/billing_models.py
TARIFF_LIMITS = {
    TariffPlan.FREE: {
        # LLM лимиты (по запросам в месяц)
        "openai_gpt_4": 0,              # FREE не может использовать GPT-4
        "openai_gpt_3_5_turbo": 100,    # 100 запросов в месяц
        "yandex_yandexgpt_latest": 50,  # 50 запросов к YandexGPT
        
        # Инструменты
        "weather_api": 50,       # 50 запросов к погоде
        "travel_suggest": 20,    # 20 предложений путешествий
        "calculator": -1,        # -1 = без лимитов
        
        # Ресурсы платформы
        "max_agents": 3,         # максимум 3 агента
        "max_flows": 2,          # максимум 2 флоу
    },
    TariffPlan.BASIC: {
        "openai_gpt_4": 10,             # 10 запросов GPT-4 в месяц
        "openai_gpt_3_5_turbo": 1000,   # 1000 запросов GPT-3.5
        "weather_api": 500,      
        "calculator": -1,
        "max_agents": 10,
        "max_flows": 5,
    },
    TariffPlan.PREMIUM: {
        "openai_gpt_4": 100,
        "openai_gpt_3_5_turbo": 10000,
        "weather_api": -1,       # без лимитов
        "calculator": -1,
        "max_agents": 50,
        "max_flows": 20,
    },
    TariffPlan.ENTERPRISE: {
        # Все без лимитов
        "openai_gpt_4": -1,
        "openai_gpt_3_5_turbo": -1,
        "weather_api": -1,
        "calculator": -1,
        "max_agents": -1,
        "max_flows": -1,
    }
}
```

## 🔧 Создание инструментов с биллингом

### В коде с декоратором @tool

```python
from app.core.tool_decorator import tool

# Бесплатный инструмент
@tool
def calculate(expression: str) -> str:
    """Вычислить математическое выражение"""
    return f"Результат: {eval(expression)}"

# Платный инструмент
@tool(cost=0.1, billing_name="weather_api")
def get_weather(city: str) -> str:
    """Получить погоду в городе (платно)"""
    return f"Погода в {city}: солнечно, 22°C"

# Инструмент с гибкими настройками
@tool(
    cost=1.0, 
    billing_name="premium_feature",
    free_for_plans=["premium", "enterprise"],  # Бесплатно для премиум планов
    max_calls_per_hour=10                      # Лимит вызовов в час
)
def premium_feature(data: str) -> str:
    """Премиум функция с гибкими настройками"""
    return f"Premium result: {data}"
```

### Параметры декоратора @tool

| Параметр | Тип | Описание | Пример |
|----------|-----|----------|---------|
| `cost` | float | Стоимость вызова в RUB | `0.1` |
| `billing_name` | str | Название для биллинга | `"weather_api"` |
| `free_for_plans` | List[str] | Бесплатные планы | `["premium"]` |
| `required_permissions` | List[str] | Требуемые разрешения | `["admin"]` |
| `max_calls_per_hour` | int | Лимит вызовов в час | `100` |

## 🗄️ Создание инструментов через БД

### Через веб-интерфейс

1. Перейти в раздел "Агенты" → "Редактировать агента"
2. В разделе "Инструменты" добавить новый ToolReference
3. Заполнить биллинг параметры:

```json
{
  "tool_id": "custom_api_tool",
  "code_mode": "inline_code",
  "inline_code": "def custom_api_call(query: str) -> str:\n    return f'API result: {query}'",
  "description": "Кастомный API инструмент",
  "cost": 0.5,
  "billing_name": "custom_api",
  "free_for_plans": ["enterprise"],
  "tariff_limits": {
    "free": 0,
    "basic": 10,
    "premium": 100,
    "enterprise": -1
  }
}
```

### Программно через Storage

```python
from app.models.core_models import ToolReference, CodeMode

tool_ref = ToolReference(
    tool_id="my_expensive_tool",
    code_mode=CodeMode.INLINE_CODE,
    inline_code="""
def expensive_operation(data: str) -> str:
    '''Дорогая операция'''
    return f'Expensive result: {data}'
""",
    description="Дорогая операция",
    cost=2.0,
    billing_name="expensive_op",
    tariff_limits={"free": 0, "basic": 5, "premium": 50}
)

# Сохранить в БД
storage = Storage()
await storage.set(f"tool:{tool_ref.tool_id}", tool_ref.model_dump_json())
```

## 🏢 Управление тарифами компаний

### Установка тарифного плана компании

```python
from app.core.storage import Storage
from app.identity.models import Company

storage = Storage()

# Получить компанию
company_data = await storage.get("company:my_company_id", force_global=True)
company = Company.model_validate_json(company_data)

# Изменить тариф
company.tariff_plan = "premium"
company.monthly_budget = 10000.0  # 10,000 рублей в месяц

# Сохранить
await storage.set(f"company:{company.company_id}", company.model_dump_json(), force_global=True)
```

### Через API (будущее)

```http
PUT /api/v1/companies/my_company_id/billing
Content-Type: application/json

{
  "tariff_plan": "premium",
  "monthly_budget": 10000.0
}
```

## 📊 Мониторинг использования

### Получение статистики компании

```python
from app.services.billing_service import BillingService

billing_service = BillingService()

# Статистика за текущий месяц
stats = await billing_service.get_company_usage_stats("company_id")

print(f"Общая стоимость: {stats['total_cost']}₽")
print(f"Общее количество вызовов: {stats['total_calls']}")

# По ресурсам
for resource, data in stats["by_resource"].items():
    print(f"{resource}: {data['cost']}₽, {data['calls']} вызовов")

# По пользователям  
for user_id, data in stats["by_user"].items():
    print(f"Пользователь {user_id}: {data['cost']}₽")
```

### Проверка лимитов

```python
# Проверить может ли компания использовать ресурс
can_use, reason = await billing_service.can_use_resource(
    user=user,
    company=company, 
    resource_name="openai_gpt_4"
)

if not can_use:
    print(f"Доступ запрещен: {reason}")
```

## ⚙️ Настройка LLM биллинга

### Стоимость LLM в конфигурации

```json
// deploy/conf.json
{
  "llm": {
    "providers": {
      "openai": {
        "models": {
          "gpt-4": {
            "max_tokens": 4000,
            "cost_per_token": 0.00003  // 0.00003₽ за токен
          },
          "gpt-3.5-turbo": {
            "max_tokens": 4000,
            "cost_per_token": 0.000002  // 0.000002₽ за токен
          }
        }
      }
    }
  }
}
```

### Автоматический биллинг LLM

LLM автоматически оборачиваются в биллинг через `LLMBillingWrapper`:

```python
# Создание LLM автоматически включает биллинг
llm = get_llm("openai", "gpt-4")  # Автоматически обернется в биллинг

# При вызове:
result = await llm.ainvoke("Привет!")
# Автоматически:
# 1. Проверяются лимиты тарифа компании
# 2. Проверяется бюджет
# 3. Рассчитывается стоимость по токенам
# 4. Записывается использование
```

## 🎛️ Переопределение параметров в БД

### Изменение стоимости инструмента

Даже если в коде указано `@tool(cost=0.1)`, в БД можно изменить:

```python
# Получить агента
agent_data = await storage.get("agent:my_agent_id")
agent_config = AgentConfig.model_validate_json(agent_data)

# Найти нужный инструмент
for tool_ref in agent_config.tools:
    if tool_ref.billing_name == "weather_api":
        # Изменить параметры
        tool_ref.cost = 0.5  # Новая стоимость
        tool_ref.free_for_plans = ["premium", "enterprise"]
        tool_ref.tariff_limits = {"free": 0, "basic": 20}
        break

# Сохранить
await storage.set(f"agent:{agent_config.agent_id}", agent_config.model_dump_json())
```

### Через веб-интерфейс

1. Открыть агента в веб-интерфейсе
2. Перейти в раздел "Инструменты"
3. Изменить поля биллинга:
   - **Стоимость** - стоимость в рублях
   - **Название для биллинга** - для группировки в статистике
   - **Бесплатно для планов** - список планов
   - **Лимиты по тарифам** - JSON с лимитами

## 📝 Примеры использования

### Создание агента с платными инструментами

```python
# app/agents/premium/agent.py
from app.core.tool_decorator import tool
from app.agents.base import BaseAgent

class PremiumAgent(BaseAgent):
    name = "Premium Agent"
    description = "Агент с платными функциями"
    prompt = "Используй доступные инструменты для обработки запросов"
    
    @staticmethod
    @tool(cost=1.0, billing_name="ai_analysis")
    def ai_analysis(text: str) -> str:
        """Анализ текста с помощью ИИ (платно)"""
        return f"AI анализ: {text}"
    
    @staticmethod
    @tool(cost=0.5, free_for_plans=["premium", "enterprise"])
    def premium_search(query: str) -> str:
        """Премиум поиск (бесплатно для премиум планов)"""
        return f"Премиум результат: {query}"
    
    @staticmethod
    @tool  # Бесплатный инструмент
    def basic_help() -> str:
        """Базовая помощь (бесплатно)"""
        return "Базовая справочная информация"
    
    tools = [ai_analysis, premium_search, basic_help]
```

### Создание компании с тарифом

```python
from app.identity.models import Company

company = Company(
    company_id="acme_corp",
    subdomain="acme",
    name="ACME Corporation",
    tariff_plan="premium",      # Премиум план
    monthly_budget=50000.0,     # 50,000₽ в месяц
    current_month_spent=0.0
)

# Сохранить в БД
storage = Storage()
await storage.set(f"company:{company.company_id}", company.model_dump_json(), force_global=True)
```

### Мониторинг использования

```python
from app.services.billing_service import BillingService

billing_service = BillingService()

# Проверить доступ к ресурсу
can_use, reason = await billing_service.can_use_resource(
    user=current_user,
    company=current_company,
    resource_name="openai_gpt_4"
)

if can_use:
    # Выполнить операцию
    result = await expensive_operation()
else:
    print(f"Доступ запрещен: {reason}")

# Получить статистику
stats = await billing_service.get_company_usage_stats(company.company_id)
print(f"Потрачено в этом месяце: {stats['total_cost']}₽")
```

## 🔧 Настройка лимитов

### Глобальные лимиты (в коде)

Редактировать `app/models/billing_models.py`:

```python
TARIFF_LIMITS = {
    TariffPlan.FREE: {
        "my_new_function": 10,    # 10 вызовов в месяц
        "expensive_api": 0,       # Запрещено на FREE
    },
    TariffPlan.BASIC: {
        "my_new_function": 100,   # 100 вызовов в месяц
        "expensive_api": 5,       # 5 вызовов в месяц
    }
}
```

### Индивидуальные лимиты (в БД)

Через ToolReference можно переопределить глобальные лимиты:

```python
tool_ref = ToolReference(
    tool_id="special_tool",
    cost=0.3,
    billing_name="special_api",
    tariff_limits={
        "free": 5,      # Переопределяем: 5 вызовов для FREE
        "basic": 50,    # 50 вызовов для BASIC  
        "premium": -1   # Без лимитов для PREMIUM
    }
)
```

### Бесплатные планы

```python
# Инструмент платный, но бесплатный для премиум планов
@tool(
    cost=2.0,
    billing_name="premium_feature", 
    free_for_plans=["premium", "enterprise"]
)
def premium_only_feature(data: str) -> str:
    """Премиум функция"""
    return f"Premium: {data}"
```

## 💳 Управление бюджетами

### Установка бюджета компании

```python
# Через код
company.monthly_budget = 25000.0  # 25,000₽ в месяц

# Сброс счетчика в начале месяца
billing_service = BillingService()
await billing_service.reset_monthly_billing(company.company_id)
```

### Автоматические проверки

Система автоматически проверяет:
1. **Тарифные лимиты** - количество использований в месяц
2. **Бюджетные лимиты** - потраченная сумма не превышает бюджет
3. **Доступность ресурса** - разрешен ли ресурс на тарифе

## 📈 Отчеты и статистика

### Структура отчета

```python
{
    "total_cost": 1250.50,        # Общая стоимость в RUB
    "total_calls": 15420,         # Общее количество вызовов
    "by_resource": {              # По ресурсам
        "openai_gpt_4": {
            "cost": 900.0,
            "calls": 300
        },
        "weather_api": {
            "cost": 350.5,
            "calls": 15120
        }
    },
    "by_user": {                  # По пользователям
        "user_123": {
            "cost": 800.0,
            "calls": 8000
        },
        "user_456": {
            "cost": 450.5,
            "calls": 7420
        }
    }
}
```

### Экспорт в CSV (будущее)

```python
# Будущая функциональность
stats = await billing_service.export_usage_csv(
    company_id="acme_corp",
    start_date="2025-09-01",
    end_date="2025-09-30"
)
```

## 🚨 Обработка ошибок

### Типичные ошибки биллинга

```python
try:
    result = await expensive_tool.ainvoke({"data": "test"})
except Exception as e:
    if "недоступен на тарифе" in str(e):
        # Ресурс недоступен на текущем тарифе
        suggest_upgrade_plan()
    elif "Превышен месячный лимит" in str(e):
        # Превышен лимит использования
        show_usage_stats()
    elif "Превышен месячный бюджет" in str(e):
        # Превышен бюджет компании
        request_budget_increase()
    else:
        # Другая ошибка
        handle_error(e)
```

### Коды ошибок

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `недоступен на тарифе free` | Ресурс запрещен на тарифе | Повысить тариф |
| `Превышен месячный лимит` | Исчерпан лимит использования | Ждать следующего месяца или повысить тариф |
| `Превышен месячный бюджет` | Исчерпан бюджет компании | Увеличить бюджет |
| `Недостаточно средств` | Недостаточно средств для операции | Пополнить бюджет |

## 🔄 Миграция и обновления

### Автоматическая миграция

При запуске приложения автоматически:
1. Сканируются все `@tool` функции в коде
2. Извлекаются биллинг параметры
3. Создаются/обновляются ToolReference в БД
4. Сохраняются метаданные биллинга

```python
# При запуске сервера
migrator = Migrator()
await migrator.run_full_migration()  # Включает миграцию биллинга
```

### Обновление существующих инструментов

```python
# Добавить биллинг к существующему инструменту
@tool(cost=0.2, billing_name="existing_tool")  # Добавить параметры
def existing_function(data: str) -> str:
    return f"Result: {data}"

# После миграции параметры попадут в БД
```

## 🧪 Тестирование

### Запуск тестов биллинга

```bash
# Все тесты биллинга
uv run python -m pytest tests/billing/ -v

# Конкретный тест
uv run python -m pytest tests/billing/test_billing_service.py::TestBillingService::test_can_use_resource_basic_plan -v

# Интеграционные тесты
uv run python -m pytest tests/billing/test_billing_service.py::test_billing_service_integration -v
```

### Структура тестов

```
tests/billing/
├── test_simple_billing.py      # Простые тесты моделей и декораторов
├── test_billing_service.py     # Тесты BillingService с БД
└── test_tool_billing.py        # Тесты ToolFactory с биллингом
```

## 🔐 Безопасность

### Принципы безопасности

1. **Валидация входных данных** - все параметры биллинга валидируются
2. **Защита от переполнения** - лимиты предотвращают чрезмерное использование  
3. **Аудит использования** - все операции записываются в БД
4. **Изоляция компаний** - данные биллинга изолированы по компаниям

### Рекомендации

- Устанавливайте разумные лимиты для FREE планов
- Регулярно мониторьте использование дорогих ресурсов
- Настраивайте алерты при приближении к лимитам
- Резервируйте бюджет на непредвиденные расходы

## 🚀 Развертывание

### Переменные окружения

```bash
# Включение биллинга (по умолчанию включен)
BILLING_ENABLED=true

# Валюта биллинга
BILLING_CURRENCY=RUB

# Интервал сброса лимитов (по умолчанию месяц)
BILLING_RESET_INTERVAL=monthly
```

### Миграция существующей системы

1. **Резервное копирование** БД перед миграцией
2. **Запуск миграции** биллинга: `migrator.run_full_migration()`
3. **Установка тарифов** для существующих компаний
4. **Настройка лимитов** под бизнес-требования
5. **Тестирование** на тестовых данных

## ❓ FAQ

**Q: Как добавить новый тарифный план?**
A: Добавить в `TariffPlan` enum и `TARIFF_LIMITS` в `billing_models.py`

**Q: Можно ли сделать инструмент бесплатным для конкретной компании?**  
A: Да, через `free_for_plans` или установив `cost=0.0` в ToolReference компании

**Q: Как работает биллинг для агентов-инструментов?**
A: Агенты как инструменты пока не тарифицируются, только их внутренние LLM/инструменты

**Q: Что происходит при превышении лимитов?**
A: Выбрасывается исключение с описанием причины, операция не выполняется

**Q: Как изменить валюту биллинга?**
A: Изменить описания полей в моделях и логику расчета стоимости

**Q: Поддерживается ли биллинг для MCP инструментов?**
A: Пока нет, но архитектура позволяет легко добавить

## 🔮 Планы развития

- [ ] API для управления тарифами и бюджетами
- [ ] Веб-интерфейс для мониторинга использования
- [ ] Алерты при приближении к лимитам
- [ ] Экспорт отчетов в CSV/Excel
- [ ] Биллинг для MCP инструментов
- [ ] Поддержка различных валют
- [ ] Система скидок и промокодов
- [ ] Интеграция с платежными системами
