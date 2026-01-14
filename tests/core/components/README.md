# E2E тесты для core компонентов

## Обзор

Playwright E2E тесты для проверки работы универсальных компонентов платформы в реальных браузерных окружениях.

**БЕЗ МОКОВ!** Все тесты используют:
- Реальные HTTP серверы для каждого сервиса
- Реальный PostgreSQL (порт 5434)
- Реальный Redis (порт 6380)
- Реальные браузеры (Chromium/Firefox/WebKit)

## Структура тестов

### platform-user компонент

Универсальный компонент отображения пользователя, тестируется в контексте всех сервисов:

| Тест файл | Сервис | Фокус тестирования |
|-----------|--------|-------------------|
| `test_platform_user_crm_playwright.py` | CRM (9003) | Базовый UI, выпадающее меню, профиль, выход |
| `test_platform_user_agents_playwright.py` | Agents (9001) | Редактирование профиля, переключение темы, настройки |
| `test_platform_user_rag_playwright.py` | RAG (9002) | Смена компании, multi-tenant функционал |
| `test_platform_user_frontend_playwright.py` | Frontend (9004) | Service-specific attributes, интеграция с AuthService |

### Группы тестов в каждом файле

Каждый тест-файл содержит 4-5 групп тестов:

1. **Базовый UI** - загрузка, видимость, отображение данных
2. **Выпадающее меню** - открытие/закрытие, содержимое
3. **Специфичные функции** - зависит от сервиса (профиль, смена компании, etc)
4. **Интеграция** - работа с сервисами (AuthService, ThemeService)
5. **Реактивность** - обработка событий, обновления состояния

## Запуск тестов

### Запуск всех тестов platform-user

```bash
pytest tests/core/components/ -v -m playwright
```

### Запуск для конкретного сервиса

```bash
# CRM
pytest tests/core/components/test_platform_user_crm_playwright.py -v -m playwright

# Agents
pytest tests/core/components/test_platform_user_agents_playwright.py -v -m playwright

# RAG
pytest tests/core/components/test_platform_user_rag_playwright.py -v -m playwright

# Frontend
pytest tests/core/components/test_platform_user_frontend_playwright.py -v -m playwright
```

### Запуск конкретной группы тестов

```bash
# Только базовый UI (CRM)
pytest tests/core/components/test_platform_user_crm_playwright.py::test_component_loads_and_visible -v

# Только меню (Agents)
pytest tests/core/components/test_platform_user_agents_playwright.py -k "menu" -v

# Только смена компании (RAG)
pytest tests/core/components/test_platform_user_rag_playwright.py -k "company" -v
```

## Архитектура тестирования

### Фикстуры (tests/fixtures/playwright.py)

| Фикстура | Назначение | Использование |
|----------|------------|---------------|
| `authenticated_browser_context` | Браузерный контекст с auth cookies | Базовая фикстура |
| `authenticated_page` | Страница с авторизацией | Для прямого использования |
| `crm_page` | CRM сервис (9003) | `await crm_page.goto("http://localhost:9003/crm/test")` |
| `agents_page` | Agents сервис (9001) | `await agents_page.goto("http://localhost:9001/agents/test")` |
| `rag_page` | RAG сервис (9002) | `await rag_page.goto("http://localhost:9002/rag/test")` |
| `frontend_page` | Frontend сервис (9004) | `await frontend_page.goto("http://localhost:9004/frontend/test")` |

### Тестовые endpoints

Все сервисы автоматически предоставляют универсальный endpoint `/{service}/test` в TESTING режиме:

```
http://localhost:9001/agents/test    - Пустая HTML страница с <div id="test-root"></div>
http://localhost:9002/rag/test       - Для инжектирования компонентов через JS
http://localhost:9003/crm/test
http://localhost:9004/frontend/test
```

### Инжектирование компонентов

Компоненты загружаются динамически через `page.evaluate()`:

```python
await page.evaluate("""
    const script = document.createElement('script');
    script.type = 'module';
    script.src = '/static/core/lib/components/platform-user.js';
    document.head.appendChild(script);
    
    script.onload = () => {
        const component = document.createElement('platform-user');
        document.getElementById('test-root').appendChild(component);
    };
""")
```

## Что тестируется

### ✅ Базовая функциональность

- Загрузка компонента в браузере
- Отображение данных пользователя (аватар, имя, email)
- Правильное определение текущего сервиса
- Доступность всех UI элементов

### ✅ Интерактивность

- Открытие/закрытие выпадающего меню
- Клики по всем пунктам меню
- Модальные окна (профиль)
- Закрытие меню при клике вне компонента

### ✅ Интеграция с сервисами

- `AuthService`: загрузка данных пользователя
- `ThemeService`: переключение темы
- `NotifyService`: уведомления
- Service-specific attributes

### ✅ Специфичные функции

- **CRM**: Базовое меню, профиль, выход
- **Agents**: Редактирование профиля, тема
- **RAG**: Смена компании (multi-tenant)
- **Frontend**: Service attrs, полный цикл

### ✅ Реактивность

- Обработка `auth-change` событий
- Автоматическое обновление данных
- Сохранение состояния при взаимодействиях

## Отладка тестов

### Включить headed режим (видимый браузер)

```bash
pytest tests/core/components/ -v -m playwright --headed
```

### Замедлить выполнение для наблюдения

```bash
pytest tests/core/components/ -v -m playwright --headed --slowmo=1000
```

### Просмотр скриншотов при ошибках

Скриншоты автоматически сохраняются в `test-results/` при падении тестов.

### Логирование

Все console.log из браузера перехватываются и выводятся в терминал:

```python
console_logs = []
page.on('console', lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

# В конце теста
for log in console_logs:
    print(log)
```

## Типичные проблемы и решения

### Тест падает с timeout

**Причина**: Компонент не загрузился за 3 секунды.

**Решение**: Увеличить `await asyncio.sleep(3.0)` до 5.0 или использовать `await page.wait_for_selector()`.

### Элемент не найден в Shadow DOM

**Причина**: Playwright по умолчанию не ищет в Shadow DOM.

**Решение**: Использовать `await component.query_selector('.class')` вместо `await page.query_selector('.class')`.

### WebSocket не подключается

**Причина**: Сервис не запущен или неправильный порт.

**Решение**: Проверить что все сервисы запущены через фикстуры.

### Меню не открывается

**Причина**: Недостаточное время ожидания после клика.

**Решение**: Добавить `await asyncio.sleep(0.3)` после `await button.click()`.

## Требования

- Python 3.12+
- Playwright (`pip install playwright`)
- Установленные браузеры (`playwright install chromium`)
- Запущенные сервисы (через pytest фикстуры)
- PostgreSQL (порт 5434)
- Redis (порт 6380)

## CI/CD

Тесты автоматически запускаются в CI пайплайне:

```yaml
- name: Run E2E Tests
  run: |
    pytest tests/core/components/ -v -m playwright --maxfail=5
```

## Добавление новых тестов

При создании нового core компонента:

1. Создать `test_{component}_playwright.py` в `tests/core/components/`
2. Использовать существующие фикстуры для сервисов
3. Следовать структуре: фикстура → группы тестов
4. Тестировать в контексте нескольких сервисов
5. Добавить описание в этот README

## Ссылки

- [Playwright документация](https://playwright.dev/python/)
- [Правила тестирования](.cursor/rules/testing.mdc)
- [Фикстуры сервисов](tests/fixtures/services.py)
- [Фикстуры Playwright](tests/fixtures/playwright.py)

