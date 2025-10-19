# 🎯 Размещение плагинов в Dashboard

## 📍 Три места размещения

Плагины могут размещаться в **трех разных местах**:

### 1️⃣ Sidebar (Основное меню)
**Для часто используемых разделов**

```python
sidebar_items = [
    {
        "id": "chats",
        "label": "dashboard.navigation.chats",
        "icon": "bi-chat-left-dots",
        "url": "/frontend/chats/",
        "order": 20,
        "type": "htmx"  # или "page"
    }
]
```

**Где:** Левая панель, основное меню  
**Кто:** Chats, Variables, History  
**Когда:** Навигационные разделы  

---

### 2️⃣ Footer (Вспомогательное меню)
**Для настроек и служебных разделов**

```python
footer_items = [
    {
        "id": "billing",
        "label": "dashboard.navigation.billing",
        "icon": "bi-credit-card",
        "url": "/frontend/billing/",
        "order": 20,
        "target": "_blank"  # опционально
    }
]
```

**Где:** Низ sidebar, перед профилем пользователя  
**Кто:** Документация, Биллинг, Настройки  
**Когда:** Вспомогательные функции  

---

### 3️⃣ Dashboard Widgets (Карточки на главной)
**Для основных приложений и модулей**

```python
dashboard_widgets = [
    {
        "id": "builder",
        "title": "Flow Builder",
        "description": "Визуальный редактор для создания flows",
        "icon": "bi-palette",
        "url": "/frontend/builder/",
        "order": 10,
        "onclick": "app.builder.openFlow()"  # опционально
    }
]
```

**Где:** Центральная часть dashboard, сетка карточек  
**Кто:** Builder, Bots, Store, Analytics  
**Когда:** Полноценные приложения, открываются на весь экран  

---

## 🎨 Визуальное расположение

```
┌─────────────────────────────────────────────────────────┐
│  HEADER                                                  │
├──────────┬──────────────────────────────────────────────┤
│          │                                               │
│ SIDEBAR  │          DASHBOARD WIDGETS                   │
│          │                                               │
│ ├─ Чаты  │  ┌─────────────┐ ┌─────────────┐            │
│ ├─ Переме│  │ 🎨 Builder  │ │ 🤖 Боты     │            │
│ ├─ История  │ Визуальный  │ │ Управление  │            │
│          │  │ редактор    │ │ ботами      │            │
│          │  └─────────────┘ └─────────────┘            │
│ FOOTER   │  ┌─────────────┐ ┌─────────────┐            │
│          │  │ 🏪 Магазин  │ │ 📊 История  │            │
│ 📚 Docs  │  │ Готовые     │ │ Диалогов    │            │
│ 💳 Billing  │ решения     │ │ и сессий    │            │
│          │  └─────────────┘ └─────────────┘            │
│ 👤 User  │                                               │
└──────────┴──────────────────────────────────────────────┘
```

---

## 📊 Текущее размещение плагинов

### Sidebar (4 плагина):
1. **Chats** - список чатов
2. **Variables** - переменные и ключи  
3. **History** - история диалогов
4. **Admin** - администрирование (только для админов)

### Footer (2 плагина):
1. **Docs** - документация
2. **Billing** - тарифы и оплата

### Dashboard Widgets (4 плагина):
1. **Builder** - визуальный редактор flows
2. **Bots** - управление ботами
3. **Store** - магазин решений
4. **History** - история (дублируется)

---

## 💡 Примеры использования

### Пример 1: Навигационный раздел

```python
class ChatsPlugin(Plugin):
    name = "chats"
    
    # Только в sidebar
    sidebar_items = [{
        "label": "Чаты",
        "icon": "bi-chat-left-dots",
        "url": "/frontend/chats/",
        "type": "htmx"  # Загружается через HTMX
    }]
    
    footer_items = []
    dashboard_widgets = []
```

**Результат:** Пункт меню в sidebar, при клике загружается содержимое через HTMX

---

### Пример 2: Полноценное приложение

```python
class BuilderPlugin(Plugin):
    name = "builder"
    
    sidebar_items = []  # Не в sidebar
    footer_items = []   # Не в footer
    
    # Только виджет на dashboard
    dashboard_widgets = [{
        "title": "Flow Builder",
        "description": "Визуальный редактор",
        "icon": "bi-palette",
        "url": "/frontend/builder/"  # Открывается на весь экран
    }]
```

**Результат:** Карточка на главной, при клике открывается полноценное приложение

---

### Пример 3: Вспомогательный раздел

```python
class DocsPlugin(Plugin):
    name = "docs"
    
    sidebar_items = []
    dashboard_widgets = []
    
    # Только в footer
    footer_items = [{
        "label": "Документация",
        "icon": "bi-book",
        "url": "/docs/",
        "target": "_blank"  # Открывается в новой вкладке
    }]
```

**Результат:** Ссылка внизу sidebar, открывается в новой вкладке

---

### Пример 4: Везде (универсальный модуль)

```python
class AnalyticsPlugin(Plugin):
    name = "analytics"
    
    # В sidebar для быстрого доступа
    sidebar_items = [{
        "label": "Аналитика",
        "icon": "bi-graph-up",
        "url": "/frontend/analytics/",
        "type": "htmx"
    }]
    
    # И виджет на dashboard
    dashboard_widgets = [{
        "title": "Аналитика",
        "description": "Статистика и отчеты",
        "icon": "bi-graph-up",
        "url": "/frontend/analytics/"
    }]
    
    footer_items = []
```

**Результат:** И в меню, и карточка на главной

---

## 🎯 Рекомендации

### Sidebar используй для:
- ✅ Навигационных разделов (Чаты, История)
- ✅ Часто используемых функций
- ✅ Списков и каталогов
- ✅ HTMX-страниц (загружаются быстро)

### Footer используй для:
- ✅ Настроек и конфигурации
- ✅ Документации и помощи
- ✅ Биллинга и подписок
- ✅ Внешних ссылок

### Dashboard Widgets используй для:
- ✅ Полноценных приложений
- ✅ Визуальных редакторов
- ✅ Интерактивных инструментов
- ✅ Основных функций платформы

---

## 🔧 Как плагин выбирает место?

Плагин сам решает, где размещаться:

```python
class MyPlugin(Plugin):
    # Заполни нужные списки
    sidebar_items = [...]    # Будет в sidebar
    footer_items = [...]     # Будет в footer
    dashboard_widgets = [...] # Будет виджетом
```

**Можно комбинировать!** Плагин может быть одновременно:
- В sidebar
- В footer  
- И виджетом на dashboard

---

## ⚙️ Параметры размещения

### Sidebar/Footer Items

```python
{
    "id": "unique_id",           # Уникальный ID
    "label": "translation.key",  # Ключ перевода или текст
    "icon": "bi-icon-name",      # Bootstrap Icon
    "url": "/frontend/path/",    # URL
    "order": 50,                 # Порядок (меньше = выше)
    "type": "htmx",              # "htmx" или "page"
    "target": "_blank"           # Только для footer (опционально)
}
```

### Dashboard Widgets

```python
{
    "id": "unique_id",
    "title": "Заголовок",              # Отображается на карточке
    "description": "Краткое описание", # Подзаголовок
    "icon": "bi-icon-name",            # Большая иконка
    "url": "/frontend/path/",          # URL при клике
    "order": 10,                       # Порядок в сетке
    "onclick": "app.module.method()"   # Кастомный обработчик (опционально)
}
```

---

## 🎉 Итог

Теперь у тебя **гибкая система размещения**:

1. **Sidebar** - для навигации
2. **Footer** - для вспомогательных функций  
3. **Dashboard Widgets** - для приложений

Каждый плагин сам решает, где ему быть! 🚀

