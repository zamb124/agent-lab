# 🔌 Плагинная система фронтенда

## Обзор

Плагинная система позволяет создавать модульные расширения фронтенда без изменения кода в `shared/`.

## Архитектура

```
app/frontend/
├── core/
│   ├── plugin_system.py       # Базовые классы (Plugin, PluginRegistry)
│   └── plugin_loader.py       # Автозагрузка плагинов
├── modules/
│   └── {module_name}/
│       ├── plugin.py          # Описание плагина
│       ├── router.py          # FastAPI роутер
│       ├── static/
│       │   ├── js/
│       │   │   └── {module_name}.module.js  # JS модуль
│       │   └── css/
│       │       └── {module_name}.css
│       └── templates/
└── shared/
    └── static/js/
        └── plugin-manager.js  # JS менеджер плагинов
```

## Создание плагина

### Шаг 1: Создать структуру

```bash
mkdir -p app/frontend/modules/my_module/{static/{js,css},templates}
touch app/frontend/modules/my_module/{__init__.py,plugin.py,router.py}
```

### Шаг 2: Описать плагин (plugin.py)

```python
from app.frontend.core.plugin_system import Plugin


class MyModulePlugin(Plugin):
    """Описание плагина"""
    
    name = "my_module"
    display_name = "Мой модуль"
    version = "1.0.0"
    description = "Краткое описание"
    author = "Agents Lab"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["my_module.css"]
    static_js = ["my_module.module.js"]
    
    sidebar_items = [
        {
            "id": "my_module",
            "label": "my_module.title",
            "icon": "bi-star",
            "url": "/frontend/my_module/",
            "order": 100,
            "type": "htmx"  # или "page"
        }
    ]
    
    def get_router(self):
        from .router import router
        return router
```

### Шаг 3: Создать роутер (router.py)

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.frontend.core.template_loader import get_templates

router = APIRouter(prefix="/frontend/my_module", tags=["my_module"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("my_module.html", {"request": request})
```

### Шаг 4: Создать JS модуль (static/js/my_module.module.js)

```javascript
export default class MyModuleModule {
    constructor(app) {
        this.app = app;
        this.name = 'my_module';
        this.version = '1.0.0';
    }
    
    async init() {
        console.log('✅ MyModule инициализирован');
        return this;
    }
    
    // Публичные методы
    doSomething() {
        console.log('MyModule doing something');
    }
    
    destroy() {
        console.log('🧹 MyModule выгружен');
    }
}
```

### Шаг 5: Использование

После перезапуска сервера плагин автоматически:

✅ Зарегистрируется в системе  
✅ Добавится в sidebar  
✅ Подключит роутер  
✅ Загрузит CSS/JS  
✅ Станет доступен через `app.my_module.doSomething()`

## Публичный API модуля

После загрузки плагин доступен через глобальный объект `app`:

```javascript
// В любом месте кода
app.my_module.doSomething();
app.builder.openFlow('flow_id');
app.bots.openBotChat('bot_id', 'Bot Name');
```

## Sidebar Items

Опции для `sidebar_items`:

```python
sidebar_items = [
    {
        "id": "unique_id",           # Уникальный ID
        "label": "translation.key",  # Ключ перевода
        "icon": "bi-icon-name",      # Bootstrap Icon
        "url": "/frontend/path/",    # URL
        "order": 50,                 # Порядок (меньше = выше)
        "type": "htmx"               # "htmx" или "page"
    }
]
```

- **type: "htmx"** - загрузка через HTMX в `#content`
- **type: "page"** - обычный переход на страницу

## Dashboard Widgets

Плагины могут добавлять виджеты на главную страницу:

```python
dashboard_widgets = [
    {
        "id": "stats_widget",
        "title": "Статистика",
        "template": "stats_widget.html",
        "order": 10,
        "width": "col-md-6"
    }
]
```

## Header Actions

Плагины могут добавлять кнопки в header:

```python
header_actions = [
    {
        "id": "export_data",
        "icon": "bi-download",
        "label": "Экспорт",
        "onclick": "app.my_module.exportData()",
        "order": 10
    }
]
```

## Lazy Loading

JS модули загружаются только когда нужны:

```javascript
export default class MyModuleModule {
    async init() {
        // Загружаем зависимости только на нужной странице
        if (this.isMyModulePage()) {
            await this.loadDependencies();
        }
        return this;
    }
    
    async loadDependencies() {
        const [Dep1, Dep2] = await Promise.all([
            import('/static/my_module/js/dep1.js'),
            import('/static/my_module/js/dep2.js')
        ]);
        
        this.Dep1 = Dep1.default;
        this.Dep2 = Dep2.default;
    }
    
    isMyModulePage() {
        return window.location.pathname.startsWith('/frontend/my_module');
    }
}
```

## Хуки жизненного цикла

```python
class MyModulePlugin(Plugin):
    async def on_load(self, app: FastAPI):
        """Вызывается при загрузке плагина"""
        print(f"Loading {self.name}...")
    
    async def on_enable(self):
        """Вызывается при включении плагина"""
        pass
    
    async def on_disable(self):
        """Вызывается при отключении плагина"""
        pass
```

## Зависимости между плагинами

```python
class AnalyticsPlugin(Plugin):
    name = "analytics"
    dependencies = ["bots", "history"]  # Требует эти плагины
```

## Hot Reload (для разработки)

```javascript
// В консоли браузера
await app.pluginManager.reload('my_module');
```

## Примеры

### Простой плагин без JS

```python
class SimplePlugin(Plugin):
    name = "simple"
    display_name = "Простой плагин"
    version = "1.0.0"
    
    static_css = ["simple.css"]
    static_js = []  # Нет JS
    
    sidebar_items = [{
        "label": "Простая страница",
        "icon": "bi-file",
        "url": "/frontend/simple/",
        "type": "htmx"
    }]
    
    def get_router(self):
        from .router import router
        return router
```

### Плагин с виджетами

```python
class DashboardStatsPlugin(Plugin):
    name = "stats"
    display_name = "Статистика"
    
    dashboard_widgets = [
        {
            "id": "user_stats",
            "title": "Статистика пользователей",
            "template": "user_stats.html",
            "order": 5
        }
    ]
    
    def get_router(self):
        from .router import router
        return router
```

## Структура реального плагина

```
app/frontend/modules/builder/
├── __init__.py
├── plugin.py                    # BuilderPlugin
├── router.py                    # FastAPI роутер
├── static/
│   ├── css/
│   │   ├── builder.css
│   │   └── element-selector.css
│   └── js/
│       ├── builder.module.js    # Главный модуль
│       ├── canvas.js            # Зависимости
│       ├── drag-drop.js
│       └── palette.js
└── templates/
    ├── builder.html
    └── components/
        └── node.html
```

## Глобальный доступ

После инициализации все плагины доступны:

```javascript
// Список загруженных плагинов
console.log(app.pluginManager.getLoadedNames());

// Получить конкретный плагин
const builder = app.pluginManager.get('builder');
const bots = app.pluginManager.get('bots');

// Или напрямую
app.builder.openFlow('flow_id');
app.bots.openBotChat('bot_id', 'Bot Name');
```

## Отладка

```javascript
// В консоли браузера
console.log('Загружено плагинов:', app.pluginManager.getLoadedNames());
console.log('Метаданные:', window.__PLUGINS__);
console.log('Builder плагин:', app.builder);
```

## Преимущества

✅ **Модульность** - каждый плагин независим  
✅ **Изоляция** - изменения не затрагивают `shared/`  
✅ **Расширяемость** - sidebar, widgets, header  
✅ **Единый API** - `app.{module}.{method}()`  
✅ **Lazy Loading** - JS загружается по требованию  
✅ **Hot Reload** - для разработки  

## Устранение проблем

### Плагин не загружается

1. Проверьте наличие `plugin.py`
2. Проверьте класс наследуется от `Plugin`
3. Проверьте `name` атрибут уникален
4. Проверьте `get_router()` возвращает роутер
5. Посмотрите логи при старте сервера

### JS модуль не загружается

1. Проверьте путь в `static_js`
2. Проверьте `export default class`
3. Проверьте `window.__PLUGINS__` в консоли
4. Проверьте консоль браузера на ошибки

### Sidebar item не появляется

1. Проверьте `sidebar_items` заполнен
2. Проверьте `order` (меньше = выше)
3. Проверьте ключ перевода в `label`
4. Проверьте права доступа `requires_role`

