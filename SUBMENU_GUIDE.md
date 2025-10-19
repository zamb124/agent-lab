# 📁 Submenu - Вложенное меню

## 🎯 Три типа пунктов меню

### 1️⃣ **Page** - Обычная ссылка
Полное обновление страницы

```python
{
    "id": "settings",
    "label": "Настройки",
    "icon": "bi-gear",
    "url": "/frontend/settings/",
    "type": "page"  # ← Обычная ссылка
}
```

---

### 2️⃣ **HTMX** - Динамическая загрузка
Подгружает контент без перезагрузки

```python
{
    "id": "chats",
    "label": "Чаты",
    "icon": "bi-chat",
    "url": "/frontend/chats/",
    "type": "htmx"  # ← HTMX загрузка
}
```

---

### 3️⃣ **Submenu** - Вложенное меню
Раскрывающееся меню с **бесконечной вложенностью**

```python
{
    "id": "analytics",
    "label": "Аналитика",
    "icon": "bi-graph-up",
    "type": "submenu",  # ← Submenu
    "children": [       # ← Вложенные пункты
        {
            "id": "analytics_dashboard",
            "label": "Дашборд",
            "icon": "bi-speedometer2",
            "url": "/frontend/analytics/dashboard",
            "type": "htmx"
        },
        {
            "id": "analytics_reports",
            "label": "Отчеты",
            "icon": "bi-file-text",
            "type": "submenu",  # ← Submenu в submenu!
            "children": [
                {
                    "id": "daily",
                    "label": "Ежедневные",
                    "icon": "bi-calendar-day",
                    "url": "/frontend/reports/daily",
                    "type": "htmx"
                }
            ]
        }
    ]
}
```

---

## 🌳 Бесконечная вложенность

```python
sidebar_items = [
    {
        "label": "Уровень 1",
        "type": "submenu",
        "children": [
            {
                "label": "Уровень 2",
                "type": "submenu",
                "children": [
                    {
                        "label": "Уровень 3",
                        "type": "submenu",
                        "children": [
                            {
                                "label": "Уровень 4",
                                "type": "htmx",
                                "url": "/deep/page"
                            }
                        ]
                    }
                ]
            }
        ]
    }
]
```

---

## 📋 Полный пример плагина

```python
from app.frontend.core.plugin_system import Plugin


class AnalyticsPlugin(Plugin):
    """Аналитика с многоуровневым меню"""
    
    name = "analytics"
    display_name = "Аналитика"
    
    sidebar_items = [
        {
            "id": "analytics",
            "label": "Аналитика",
            "icon": "bi-graph-up",
            "type": "submenu",
            "order": 50,
            "children": [
                # Уровень 1: Дашборд
                {
                    "id": "dashboard",
                    "label": "Дашборд",
                    "icon": "bi-speedometer2",
                    "url": "/frontend/analytics/dashboard",
                    "type": "htmx"  # ← HTMX загрузка
                },
                
                # Уровень 1: Отчеты (submenu)
                {
                    "id": "reports",
                    "label": "Отчеты",
                    "icon": "bi-file-earmark-text",
                    "type": "submenu",  # ← Вложенное submenu
                    "children": [
                        # Уровень 2: Ежедневные
                        {
                            "id": "daily",
                            "label": "Ежедневные",
                            "icon": "bi-calendar-day",
                            "url": "/frontend/reports/daily",
                            "type": "htmx"
                        },
                        
                        # Уровень 2: Ежемесячные
                        {
                            "id": "monthly",
                            "label": "Ежемесячные",
                            "icon": "bi-calendar-month",
                            "url": "/frontend/reports/monthly",
                            "type": "htmx"
                        },
                        
                        # Уровень 2: Кастомные (еще один submenu!)
                        {
                            "id": "custom",
                            "label": "Кастомные",
                            "icon": "bi-sliders",
                            "type": "submenu",
                            "children": [
                                # Уровень 3
                                {
                                    "id": "custom_create",
                                    "label": "Создать отчет",
                                    "icon": "bi-plus",
                                    "url": "/frontend/reports/custom/create",
                                    "type": "page"  # ← Обычная страница
                                },
                                {
                                    "id": "custom_templates",
                                    "label": "Шаблоны",
                                    "icon": "bi-files",
                                    "url": "/frontend/reports/templates",
                                    "type": "htmx"
                                }
                            ]
                        }
                    ]
                },
                
                # Уровень 1: Экспорт
                {
                    "id": "export",
                    "label": "Экспорт данных",
                    "icon": "bi-download",
                    "url": "/frontend/analytics/export",
                    "type": "page"  # ← Полный переход
                }
            ]
        }
    ]
    
    def get_router(self):
        from fastapi import APIRouter
        return APIRouter()
```

---

## 🎨 Как это выглядит

```
SIDEBAR:

📊 Аналитика  ▼
  ├─ 📈 Дашборд (HTMX)
  ├─ 📄 Отчеты  ▼
  │   ├─ 📅 Ежедневные (HTMX)
  │   ├─ 📆 Ежемесячные (HTMX)
  │   └─ 🎚️ Кастомные  ▼
  │       ├─ ➕ Создать отчет (Page)
  │       └─ 📁 Шаблоны (HTMX)
  └─ 💾 Экспорт данных (Page)
```

---

## 🔄 Поведение

### Submenu:
- Клик → раскрывается/сворачивается
- Стрелка ↓ поворачивается при раскрытии
- Анимация плавного раскрытия

### HTMX:
- Клик → загружает контент в `#content`
- URL обновляется в адресной строке
- Нет перезагрузки страницы

### Page:
- Клик → обычный переход
- Полная перезагрузка страницы
- Новый URL

---

## 💡 Когда что использовать

### **Page** используй для:
- ✅ Тяжелых страниц (Builder, Canvas)
- ✅ Внешних ссылок
- ✅ Страниц с собственной навигацией

### **HTMX** используй для:
- ✅ Быстрых переходов
- ✅ Списков и таблиц
- ✅ Форм и редактирования

### **Submenu** используй для:
- ✅ Группировки разделов
- ✅ Многоуровневой навигации
- ✅ Организации сложной структуры

---

## 📦 Обязательные поля

### Для всех типов:
```python
{
    "id": "unique_id",      # Уникальный ID
    "label": "Название",    # Текст или ключ перевода
    "icon": "bi-icon",      # Bootstrap Icon
    "type": "page|htmx|submenu"
}
```

### Для Page и HTMX:
```python
{
    "url": "/frontend/path/"  # URL страницы
}
```

### Для Submenu:
```python
{
    "children": [...]  # Массив вложенных пунктов
}
```

---

## 🎯 Примеры из реальной жизни

### Настройки:
```python
{
    "label": "Настройки",
    "icon": "bi-gear",
    "type": "submenu",
    "children": [
        {"label": "Профиль", "type": "htmx", "url": "/settings/profile"},
        {"label": "Безопасность", "type": "htmx", "url": "/settings/security"},
        {"label": "Уведомления", "type": "htmx", "url": "/settings/notifications"}
    ]
}
```

### Управление:
```python
{
    "label": "Управление",
    "icon": "bi-tools",
    "type": "submenu",
    "children": [
        {
            "label": "Пользователи",
            "type": "submenu",
            "children": [
                {"label": "Список", "type": "htmx", "url": "/users"},
                {"label": "Роли", "type": "htmx", "url": "/users/roles"}
            ]
        },
        {
            "label": "Компании",
            "type": "htmx",
            "url": "/companies"
        }
    ]
}
```

---

## ✨ Фишки

### Автоматическое закрытие на мобильных
```python
# HTMX пункты автоматически закрывают меню на мобильных
{
    "type": "htmx",
    "url": "/page"
    # При клике на мобильном sidebar автоматически закроется
}
```

### Сохранение состояния
```javascript
// Submenu запоминает состояние (открыт/закрыт)
// при переходах между страницами
```

### Плавная анимация
```css
/* Submenu плавно раскрывается */
transition: max-height 0.3s ease;
```

---

## 🎊 Итог

Теперь у тебя **три типа навигации**:

1. **Page** - полный переход
2. **HTMX** - динамическая загрузка
3. **Submenu** - вложенное меню с бесконечной глубиной

**Можно комбинировать как угодно!** 🚀

