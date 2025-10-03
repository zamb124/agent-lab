# 🎨 Frontend Architecture - Agents Lab

> **Модульный фронтенд на базе HTMX с Backend-Driven подходом**

Основан на концепции автогенерации HTML из Pydantic моделей через рекурсивный рендеринг.

---

## 📋 Содержание

- [Архитектура](#-архитектура)
- [Структура директорий](#-структура-директорий)
- [Детальное описание файлов](#-детальное-описание-файлов)
- [Принципы работы](#-принципы-работы)
- [Добавление нового модуля](#-добавление-нового-модуля)

---

## 🏗 Архитектура

### Ключевые принципы:

1. **Backend-Driven Frontend** - Pydantic модели автоматически генерируют HTML
2. **Модульность** - каждый крупный модуль (chat, builder, landing) изолирован
3. **Разделение ответственности** - API (JSON) отдельно от Pages (HTML) отдельно от WebSockets
4. **Единая точка входа** - `core/template_loader.py` для всех шаблонов
5. **HTMX-first** - минимум JavaScript, максимум HTMX

### Схема работы:

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Application                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   API        │  │   PAGES      │  │  WEBSOCKETS  │      │
│  │  (JSON)      │  │   (HTML)     │  │   (WS)       │      │
│  │              │  │              │  │              │      │
│  │ /frontend/   │  │ /frontend/   │  │ /ws/         │      │
│  │  builder/    │  │  auth        │  │ /frontend/   │      │
│  │  flows/      │  │  dashboard   │  │  chat/ws/    │      │
│  │  agents/     │  │              │  │              │      │
│  │  tools/      │  │              │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              CORE (Infrastructure)                    │   │
│  │  - template_loader.py (единый Jinja2Templates)       │   │
│  │  - websocket_manager.py (менеджер соединений)        │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    MODULES                            │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐     │   │
│  │  │  Builder   │  │   Chat     │  │  Landing   │     │   │
│  │  │  router.py │  │  router.py │  │ templates/ │     │   │
│  │  │ templates/ │  │ templates/ │  │            │     │   │
│  │  └────────────┘  └────────────┘  └────────────┘     │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    SHARED                             │   │
│  │  templates/  - общие шаблоны (base.html, fields/)    │   │
│  │  static/     - CSS, JS, изображения                  │   │
│  │    ├── css/ - общие стили                            │   │
│  │    ├── js/  - общие скрипты                          │   │
│  │    ├── builder/ - модульные CSS/JS builder           │   │
│  │    ├── chat/    - модульные CSS/JS chat              │   │
│  │    └── landing/ - модульные CSS/JS landing           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Структура директорий

```
backend/app/frontend/
├── 📄 Корневые файлы (ядро системы)
│   ├── __init__.py                    # Инициализация пакета
│   ├── field_extensions.py            # ⭐ ЯДРО: Monkey patch для BaseModel/Field
│   ├── environment.py                 # Jinja2 для backend рендеринга
│   ├── model_registry.py              # Реестр моделей по storage_prefix
│   └── wrappers.py                    # ModelListWrapper для списков
│
├── 🔧 CORE/ (инфраструктура)
│   ├── __init__.py
│   ├── template_loader.py             # ✅ Единый Jinja2Templates для всех
│   └── websocket_manager.py           # Менеджер WebSocket соединений
│
├── 🔌 API/ (JSON CRUD endpoints)
│   ├── __init__.py
│   ├── models.py                      # CRUD операции для моделей
│   ├── flows.py                       # API для flows (GET/POST/PUT/DELETE)
│   ├── agents.py                      # API для agents
│   └── tools.py                       # API для tools
│
├── 📄 PAGES/ (HTML страницы)
│   ├── __init__.py
│   ├── public.py                      # Landing page (/)
│   ├── auth.py                        # Авторизация, выбор/создание компании
│   └── dashboard.py                   # Dashboard, модели, FASHN
│
├── 🔗 WEBSOCKETS/ (WebSocket endpoints)
│   ├── __init__.py
│   ├── notifications.py               # Уведомления о моделях
│   └── chat.py                        # Чат с агентами
│
├── 🧩 MODULES/ (изолированные модули)
│   ├── __init__.py
│   │
│   ├── builder/                       # Builder для flows
│   │   ├── __init__.py
│   │   ├── router.py                  # /frontend/builder/*
│   │   └── templates/
│   │       ├── builder.html           # Главная страница
│   │       ├── components/            # Переиспользуемые компоненты
│   │       │   ├── flow_card.html
│   │       │   ├── agent_card.html
│   │       │   └── node.html
│   │       └── modals/
│   │           └── flow_editor.html
│   │
│   ├── chat/                          # Чат система
│   │   ├── __init__.py
│   │   ├── router.py                  # /frontend/chat/*
│   │   └── templates/
│   │       ├── chat.html              # Полная страница чата
│   │       ├── chat_widget.html       # Виджет для встраивания
│   │       └── chat_widget_inline.html # Инлайн виджет
│   │
│   ├── billing/                       # Биллинг и тарификация
│   │   ├── __init__.py
│   │   ├── router.py                  # /frontend/billing/*
│   │   └── templates/
│   │       └── billing.html           # Страница биллинга
│   │
│   └── landing/                       # Landing page
│       ├── __init__.py
│       └── templates/
│           ├── base_landing.html      # Базовый layout для landing
│           └── landing.html           # Контент landing page
│
└── 🌐 SHARED/ (общие ресурсы)
    │
    ├── templates/                     # Общие шаблоны
    │   ├── base.html                  # Базовый layout для всех страниц
    │   ├── auth.html                  # Страница авторизации
    │   ├── dashboard.html             # Dashboard layout
    │   ├── index.html                 # Индексная страница
    │   ├── fashn.html                 # FASHN виртуальная примерка
    │   ├── create_company.html        # Создание компании
    │   ├── select_company.html        # Выбор компании
    │   │
    │   ├── fields/                    # ⭐ Шаблоны для рекурсивного рендеринга
    │   │   ├── base_field.html        # Базовый шаблон поля
    │   │   ├── str.html               # String поле
    │   │   ├── int.html               # Integer поле
    │   │   ├── float.html             # Float поле
    │   │   ├── bool.html              # Boolean поле
    │   │   ├── datetime.html          # DateTime поле
    │   │   ├── enum.html              # Enum поле
    │   │   ├── list.html              # List поле
    │   │   ├── list_str.html          # List[str]
    │   │   ├── list_dict_str_any.html # List[Dict[str, Any]]
    │   │   ├── list_toolreference.html # List[ToolReference]
    │   │   ├── dict.html              # Dict поле
    │   │   ├── dict_str_any.html      # Dict[str, Any]
    │   │   ├── dict_str_str.html      # Dict[str, str]
    │   │   ├── basemodel.html         # Вложенные модели
    │   │   └── historysource.html     # Специальные типы
    │   │
    │   ├── modals/                    # Модальные окна
    │   │   ├── modal.html             # Базовый модал
    │   │   ├── inline_edit.html       # Инлайн редактирование
    │   │   └── success.html           # Уведомления об успехе
    │   │
    │   ├── models/                    # Кастомные шаблоны моделей
    │   │   ├── ModelListWrapper.html  # Список моделей
    │   │   └── ModelListWrapper_table.html # Таблица моделей
    │   │
    │   └── wrappers/                  # Обертки для разных режимов
    │       ├── table.html             # Таблица
    │       ├── table_row.html         # Строка таблицы
    │       ├── form.html              # Форма
    │       └── compact.html           # Компактный вид
    │
    └── static/                        # Статические файлы (mount на /static)
        │
        ├── css/                       # Общие стили
        │   ├── style.css              # Главный файл (импортирует все)
        │   ├── variables.css          # CSS переменные (темы)
        │   ├── base.css               # Базовые стили + утилиты
        │   ├── components.css         # Компоненты (кнопки, карточки)
        │   ├── layout.css             # Лейаут (сайдбар, хедер)
        │   ├── fields.css             # Стили для полей форм
        │   └── fashn.css              # Стили для FASHN примерки
        │
        ├── js/                        # Общие JavaScript модули
        │   ├── app.js                 # ⭐ Главный класс APP
        │   ├── chat.js                # Чат функциональность
        │   ├── fashn.js               # FASHN виртуальная примерка
        │   ├── htmx-manager.js        # Менеджер HTMX
        │   ├── layout-manager.js      # Менеджер лейаута
        │   └── theme-manager.js       # Менеджер тем
        │
        ├── img/                       # Изображения
        │   ├── empty.png
        │   ├── fashn_back.jpg
        │   └── main.png
        │
        ├── builder/                   # Модульные файлы Builder
        │   ├── css/
        │   │   ├── builder.css        # Главные стили builder
        │   │   ├── canvas.css         # Стили канваса
        │   │   └── sidebar.css        # Стили сайдбара
        │   └── js/
        │       ├── builder.js         # Главный класс Builder
        │       ├── canvas.js          # Работа с канвасом
        │       ├── drag-drop.js       # Drag & Drop
        │       └── sidebar.js         # Сайдбар Builder
        │
        ├── chat/                      # Модульные файлы Chat
        │   └── js/
        │       └── chat.js            # (дубликат в js/)
        │
        └── landing/                   # Модульные файлы Landing
            └── css/
                └── landing.css        # Стили landing page
```

---

## 📝 Детальное описание файлов

### 🔧 Корневые файлы (Ядро системы)

#### `field_extensions.py` ⭐ ЯДРО
**Monkey patch для Pydantic моделей и полей**

- Добавляет метод `.render()` к `BaseModel` - рекурсивный рендеринг модели в HTML
- Добавляет метод `.render()` к `Field` - рендеринг поля по его типу
- Динамически определяет шаблон по типу: `List[str]` → `fields/list_str.html`
- Поддерживает режимы отображения: `form`, `table`, `compact`
- Обрабатывает группы пользователей для условной видимости полей

**Ключевые функции:**
- `get_template_name_from_type()` - определяет имя шаблона по аннотации типа
- `FrontendFieldInfo` - расширенная информация о поле (readonly, hidden, groups)

#### `environment.py`
**Настройка Jinja2 для backend рендеринга**

- Создает Jinja2 Environment для `shared/templates/`
- Используется в `api/models.py` для рендеринга field шаблонов
- Функция `render_template()` - рендерит шаблон с контекстом
- Функция `template_exists()` - проверяет существование шаблона

#### `model_registry.py`
**Реестр моделей по storage_prefix**

- Автоматически регистрирует все модели с `Config.storage_prefix`
- Позволяет получить класс модели по префиксу: `ModelRegistry.get_model_class("flow")`
- Используется в `api/models.py` для CRUD операций

#### `wrappers.py`
**ModelListWrapper для списков моделей**

- Обертка для списка моделей с поддержкой разных режимов отображения
- Использует кастомные шаблоны: `models/ModelListWrapper_table.html`

---

### 🔧 CORE/ (Инфраструктура)

#### `core/template_loader.py` ✅
**Единый загрузчик шаблонов для всех модулей**

- Автоматически находит все `templates/` директории в `shared/` и `modules/*/`
- Создает единый `Jinja2Templates` с правильными приоритетами
- Используется всеми роутерами через `get_templates()`

**Приоритет загрузки:**
1. `shared/templates/` (общие шаблоны)
2. `modules/*/templates/` (модульные шаблоны)

#### `core/websocket_manager.py`
**Менеджер WebSocket соединений** (legacy, можно удалить)

---

### 🔌 API/ (JSON CRUD endpoints)

#### `api/models.py`
**CRUD операции для Pydantic моделей**

**Endpoints:**
- `GET /frontend/models/{model_type}?view=table` - список моделей
- `GET /frontend/models/{model_type}/{model_id}` - конкретная модель
- `POST /frontend/models/{model_type}` - создание модели
- `PUT /frontend/models/{model_type}/{model_id}` - обновление
- `DELETE /frontend/models/{model_type}/{model_id}` - удаление

**Особенности:**
- Автоматически определяет класс модели через `ModelRegistry`
- Использует `model.render(view_mode=...)` для генерации HTML
- Отправляет уведомления через `notify_model_updated()`

#### `api/flows.py`
**API для работы с flows**

**Endpoints:**
- `GET /frontend/builder/flows/` - список flows
- `GET /frontend/builder/flows/{flow_id}` - конкретный flow
- `POST /frontend/builder/flows/` - создание flow
- `PUT /frontend/builder/flows/{flow_id}` - обновление
- `DELETE /frontend/builder/flows/{flow_id}` - удаление

#### `api/agents.py`
**API для работы с agents**

Аналогично `flows.py`, но для agents.

#### `api/tools.py`
**API для работы с tools**

Аналогично `flows.py`, но для tools.

---

### 📄 PAGES/ (HTML страницы)

#### `pages/public.py`
**Публичные страницы**

- `GET /` - landing page

#### `pages/auth.py`
**Авторизация и управление компаниями**

- `GET /frontend/auth` - страница авторизации
- `GET /frontend/select-company` - выбор компании
- `GET /frontend/create-company` - создание компании

#### `pages/dashboard.py`
**Dashboard и страницы моделей**

- `GET /frontend/` - главная страница (редирект)
- `GET /frontend/dashboard` - dashboard
- `GET /frontend/models/{model_type}` - страница модели
- `GET /frontend/fashn` - FASHN виртуальная примерка

---

### 🔗 WEBSOCKETS/ (WebSocket endpoints)

#### `websockets/notifications.py`
**WebSocket для уведомлений о моделях**

- `WS /ws/notifications` - глобальные уведомления
- Функция `notify_model_updated()` - отправляет уведомление всем клиентам

#### `websockets/chat.py`
**WebSocket для чата с агентами**

- `WS /frontend/chat/ws/chat?session_id=...` - чат с агентом
- Polling уведомлений для каждой сессии
- Обработка сообщений пользователя

---

### 🧩 MODULES/ (Изолированные модули)

#### `modules/builder/router.py`
**Роутер для Builder страниц**

- `GET /frontend/builder/` - главная страница builder
- `GET /frontend/builder/flow/{flow_id}` - редактирование flow

#### `modules/chat/router.py`
**Роутер для Chat страниц**

- `GET /frontend/chat/` - главная страница чата
- `GET /frontend/chat/widget` - виджет чата

#### `modules/billing/router.py`
**Роутер для страниц биллинга и тарификации**

- `GET /frontend/billing/` - главная страница биллинга
- `GET /frontend/billing/api/stats` - API для получения статистики
- `POST /frontend/billing/api/payment` - инициализация платежа (заглушка)

#### `modules/landing/`
**Модуль landing page**

Только templates, без роутера (использует `pages/public.py`).

---

### 🌐 SHARED/ (Общие ресурсы)

#### Templates

**Базовые layouts:**
- `base.html` - базовый layout с темной темой, HTMX, навигацией
- `base_landing.html` - базовый layout для landing page

**Страницы:**
- `auth.html` - форма авторизации
- `dashboard.html` - layout dashboard с сайдбаром
- `index.html` - индексная страница
- `fashn.html` - FASHN виртуальная примерка
- `create_company.html` - создание компании
- `select_company.html` - выбор компании

**Fields/** ⭐ Рекурсивный рендеринг
- Каждый файл - шаблон для конкретного типа поля
- `base_field.html` - базовый fallback
- Поддержка всех Python типов + Pydantic специальных типов

**Modals/**
- `modal.html` - базовая структура модального окна
- `inline_edit.html` - инлайн редактирование вложенных моделей
- `success.html` - уведомления об успехе

**Models/**
- Кастомные шаблоны для конкретных моделей
- `ModelListWrapper.html` - список моделей (cards режим)
- `ModelListWrapper_table.html` - список моделей (table режим)

**Wrappers/**
- `table.html` - обертка для таблицы
- `table_row.html` - строка таблицы с inline edit
- `form.html` - обертка для формы
- `compact.html` - компактный вид

#### Static

**CSS:**
- `style.css` - главный файл, импортирует все модули
- `variables.css` - CSS переменные (цвета, размеры, тени)
- `base.css` - reset + базовые стили + утилиты
- `components.css` - переиспользуемые компоненты (кнопки, карточки)
- `layout.css` - структура страницы (сайдбар, хедер)
- `fields.css` - стили для полей форм
- `fashn.css` - стили для FASHN примерки

**JS:**
- `app.js` - главный класс APP (инициализация, auth, HTMX, UI)
- `chat.js` - чат (WebSocket, отправка/получение сообщений)
- `fashn.js` - FASHN (загрузка изображений, предпросмотр)
- `htmx-manager.js` - расширенное управление HTMX
- `layout-manager.js` - управление лейаутом (сайдбар, адаптивность)
- `theme-manager.js` - переключение светлой/темной темы

**Builder:** (модульные CSS/JS)
- `builder.css` - главные стили
- `canvas.css` - стили канваса (сетка, ноды, связи)
- `sidebar.css` - стили сайдбара
- `builder.js` - главный класс Builder
- `canvas.js` - работа с канвасом (zoom, pan, drag)
- `drag-drop.js` - drag & drop flows/agents/tools
- `sidebar.js` - сайдбар (загрузка, поиск, фильтрация)

**Landing:** (модульные CSS)
- `landing.css` - стили landing page

**Chat:** (модульные JS)
- `chat.js` - дубликат в `js/` (для импорта из `app.js`)

---

## 🔄 Принципы работы

### 1. Рекурсивный рендеринг

```python
# Модель
class FlowConfig(BaseModel):
    flow_id: str
    name: str
    agents: List[AgentConfig]

# Вызов
flow.render(view_mode="form")

# Что происходит:
# 1. field_extensions.py добавляет метод .render() к BaseModel
# 2. Итерация по всем полям модели
# 3. Для каждого поля вызывается field.render()
# 4. Поле определяет свой шаблон: str → fields/str.html
# 5. Если поле - BaseModel → рекурсивно вызывается .render()
# 6. Результат - HTML вся модель с вложенными моделями
```

### 2. Динамическое определение шаблонов

```python
# Типы → Шаблоны
str              → fields/str.html
int              → fields/int.html
List[str]        → fields/list_str.html
Dict[str, Any]   → fields/dict_str_any.html
Optional[int]    → fields/int.html (Optional игнорируется)
BaseModel        → fields/basemodel.html (рекурсивно)
```

### 3. Единый template loader

```python
from app.frontend.core.template_loader import get_templates

templates = get_templates()
return templates.TemplateResponse("builder.html", {"request": request})
```

**Порядок поиска:**
1. `shared/templates/builder.html`
2. `modules/builder/templates/builder.html`
3. `modules/chat/templates/builder.html`
4. И так далее по всем модулям

### 4. Модульная организация static

```html
<!-- В shared/templates/base.html -->
<link rel="stylesheet" href="/static/css/style.css">
<script src="/static/js/app.js"></script>

<!-- В modules/builder/templates/builder.html -->
<link rel="stylesheet" href="{{ url_for('static', path='builder/css/builder.css') }}">
<script src="/static/builder/js/builder.js"></script>

<!-- В modules/landing/templates/base_landing.html -->
<link rel="stylesheet" href="/static/landing/css/landing.css">
```

**Все статические файлы доступны через один mount:**
```python
app.mount("/static", StaticFiles(directory="frontend/shared/static"), name="static")
```

---

## ➕ Добавление нового модуля

### 1. Создать структуру

```bash
mkdir -p modules/my_module/templates
touch modules/my_module/__init__.py
touch modules/my_module/router.py
```

### 2. Создать роутер

```python
# modules/my_module/router.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.frontend.core.template_loader import get_templates

router = APIRouter(prefix="/frontend/my_module", tags=["my-module"])
templates = get_templates()

@router.get("/", response_class=HTMLResponse)
async def my_module_index(request: Request):
    return templates.TemplateResponse("my_module.html", {"request": request})
```

### 3. Создать шаблон

```html
<!-- modules/my_module/templates/my_module.html -->
{% extends "base.html" %}

{% block title %}My Module{% endblock %}

{% block head %}
<link rel="stylesheet" href="/static/my_module/css/my_module.css">
{% endblock %}

{% block content %}
<div>My Module Content</div>
{% endblock %}

{% block scripts %}
<script src="/static/my_module/js/my_module.js"></script>
{% endblock %}
```

### 4. Создать static файлы

```bash
mkdir -p shared/static/my_module/css
mkdir -p shared/static/my_module/js
touch shared/static/my_module/css/my_module.css
touch shared/static/my_module/js/my_module.js
```

### 5. Подключить в main.py

```python
from app.frontend.modules.my_module import router as my_module

app.include_router(my_module.router, tags=["my-module"])
```

### 6. Готово! 🎉

Модуль автоматически:
- Загружает свои templates через `core/template_loader.py`
- Получает доступ к статике через `/static/my_module/`
- Изолирован от других модулей

---

## 🎯 Ключевые особенности

### ✅ Что делать НУЖНО:

1. **Использовать единый template loader** - `get_templates()`
2. **Именовать шаблоны уникально** - `builder.html`, не `index.html`
3. **Размещать модульные CSS/JS в `shared/static/module_name/`**
4. **Использовать рекурсивный рендеринг** - `model.render(view_mode="form")`
5. **Добавлять новые типы полей в `shared/templates/fields/`**

### ❌ Что делать НЕ НУЖНО:

1. **Создавать свой Jinja2Templates** - используйте `get_templates()`
2. **Создавать `index.html` в модулях** - конфликт имен с `shared/templates/index.html`
3. **Mount отдельные static директории** - используйте общую структуру
4. **Хардкодить типы в templates** - используйте динамическое определение
5. **Дублировать CSS/JS** - выносите общее в `shared/static/css|js/`

---

## 📊 Статистика

- **Всего файлов:** ~90
- **Python файлы:** 16
- **HTML templates:** 42
- **CSS файлы:** 11
- **JS файлы:** 13
- **Изображения:** 3

---

## 🔗 Связанные документы

- [CONFIG_README.md](/CONFIG_README.md) - конфигурация приложения
- [BILLING_README.md](/BILLING_README.md) - биллинг система

---

**Автор:** Viktor Shved  
**Дата:** 2025-10-03  
**Версия:** 2.0 (после реорганизации)
