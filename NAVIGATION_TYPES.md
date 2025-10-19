# 🎯 Типы навигации в плагинах

## 📌 Краткая справка

```python
# 1. Page - обычная ссылка (полное обновление)
{
    "type": "page",
    "url": "/frontend/builder/"
}

# 2. HTMX - динамическая загрузка (без перезагрузки)
{
    "type": "htmx",
    "url": "/frontend/chats/"
}

# 3. Submenu - вложенное меню (раскрывается)
{
    "type": "submenu",
    "children": [...]
}
```

---

## 🎨 Визуальная разница

```
SIDEBAR:

┌────────────────────────┐
│ 🤖 Боты (page)         │ ← Клик → полная перезагрузка
├────────────────────────┤
│ 💬 Чаты (htmx)         │ ← Клик → загрузка в #content
├────────────────────────┤
│ 📊 Аналитика (submenu) ▼ ← Клик → раскрывается меню
│   ├─ 📈 Дашборд        │
│   ├─ 📄 Отчеты ▼       │
│   │   ├─ Ежедневные    │
│   │   └─ Ежемесячные   │
│   └─ 💾 Экспорт        │
└────────────────────────┘
```

---

## 🔄 Поведение

### Page:
```python
{
    "label": "Builder",
    "icon": "bi-palette",
    "url": "/frontend/builder/",
    "type": "page"
}
```
- ✅ Полная перезагрузка страницы
- ✅ Новый URL в адресной строке
- ✅ Браузер добавляет в историю
- 💡 Используй для тяжелых страниц

---

### HTMX:
```python
{
    "label": "Чаты",
    "icon": "bi-chat",
    "url": "/frontend/chats/",
    "type": "htmx"
}
```
- ✅ Загружает HTML в `#content`
- ✅ URL обновляется (push state)
- ✅ Нет перезагрузки
- ✅ Быстрая загрузка
- 💡 Используй для быстрых переходов

---

### Submenu:
```python
{
    "label": "Настройки",
    "icon": "bi-gear",
    "type": "submenu",
    "children": [
        {
            "label": "Профиль",
            "url": "/settings/profile",
            "type": "htmx"
        }
    ]
}
```
- ✅ Раскрывается/сворачивается
- ✅ Бесконечная вложенность
- ✅ Анимация раскрытия
- ✅ Дети могут быть любого типа
- 💡 Используй для группировки

---

## 📋 Примеры плагинов

### 1. Простой плагин (Page)

```python
class BuilderPlugin(Plugin):
    name = "builder"
    
    dashboard_widgets = [{
        "title": "Flow Builder",
        "url": "/frontend/builder/"
        # type не указан = page по умолчанию
    }]
```

---

### 2. Навигационный плагин (HTMX)

```python
class ChatsPlugin(Plugin):
    name = "chats"
    
    sidebar_items = [{
        "label": "Чаты",
        "icon": "bi-chat",
        "url": "/frontend/chats/",
        "type": "htmx"  # ← Быстрая загрузка
    }]
```

---

### 3. Многоуровневый плагин (Submenu)

```python
class AdminPlugin(Plugin):
    name = "admin"
    
    sidebar_items = [{
        "label": "Администрирование",
        "icon": "bi-shield-lock",
        "type": "submenu",
        "children": [
            {
                "label": "Пользователи",
                "icon": "bi-people",
                "url": "/admin/users",
                "type": "htmx"
            },
            {
                "label": "Настройки",
                "icon": "bi-gear",
                "type": "submenu",  # ← Submenu в submenu!
                "children": [
                    {
                        "label": "Общие",
                        "url": "/admin/settings/general",
                        "type": "htmx"
                    }
                ]
            }
        ]
    }]
```

---

## 🎯 Когда что использовать

### Page:
- Полноценные приложения (Builder, Analytics)
- Страницы с WebSocket
- Страницы с canvas/3D
- Внешние ссылки

### HTMX:
- Списки (Чаты, История)
- Формы
- Таблицы
- Быстрая навигация

### Submenu:
- Группировка разделов
- Многоуровневая навигация
- Настройки
- Администрирование

---

## ⚙️ Технические детали

### HTMX атрибуты:
```html
<a href="/frontend/chats/"
   hx-get="/frontend/chats/"
   hx-target="#content"
   hx-push-url="true"
   hx-indicator="#content-loading">
```

### Submenu структура:
```html
<div class="sidebar-nav-item">
    <div class="sidebar-nav-submenu" onclick="toggle()">
        Аналитика ▼
    </div>
    <div class="sidebar-nav-submenu-items">
        <!-- Вложенные пункты -->
    </div>
</div>
```

---

## 💡 Советы

### Комбинируй типы:
```python
sidebar_items = [
    # HTMX для списков
    {"label": "Чаты", "type": "htmx", ...},
    
    # Submenu для группировки
    {
        "label": "Настройки",
        "type": "submenu",
        "children": [
            # HTMX внутри submenu
            {"label": "Профиль", "type": "htmx", ...},
            # Page для тяжелой страницы
            {"label": "Интеграции", "type": "page", ...}
        ]
    }
]
```

### Используй иконки:
```python
# Bootstrap Icons
"icon": "bi-house"      # 🏠
"icon": "bi-chat"       # 💬
"icon": "bi-gear"       # ⚙️
"icon": "bi-graph-up"   # 📊
```

---

## 🎊 Итог

**Три мощных типа навигации:**

1. **Page** - классика
2. **HTMX** - скорость
3. **Submenu** - структура

**Выбирай правильный тип для каждой задачи!** 🚀

