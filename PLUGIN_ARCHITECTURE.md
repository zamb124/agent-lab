# 🎉 Плагинная архитектура фронтенда - ГОТОВО!

## ✅ Что сделано

### 1. Ядро системы
- ✅ `app/frontend/core/plugin_system.py` - базовые классы Plugin и PluginRegistry
- ✅ `app/frontend/core/plugin_loader.py` - автозагрузка плагинов
- ✅ `app/frontend/shared/static/js/plugin-manager.js` - JS менеджер плагинов
- ✅ Обновлен `app.js` с поддержкой плагинов

### 2. Интеграция
- ✅ `main.py` - автозагрузка плагинов при старте
- ✅ `dashboard.py` - динамическая передача данных плагинов
- ✅ `dashboard.html` - динамический рендеринг sidebar из плагинов

### 3. Созданы плагины

**Готовые плагины с JS модулями:**
- ✅ **builder** - визуальный редактор flows
- ✅ **bots** - управление ботами
- ✅ **store** - магазин готовых решений

**Готовые плагины без JS:**
- ✅ **history** - история диалогов
- ✅ **variables** - переменные и ключи
- ✅ **chats** - список чатов
- ✅ **billing** - биллинг
- ✅ **admin** - администрирование
- ✅ **chat** - виджет чата

## 🚀 Как запустить

```bash
# Запустить сервер
uv run python run.py
```

При старте увидите:
```
🔌 Загрузка плагинов фронтенда...
  ✅ Builder (1.0.0)
  ✅ Боты (1.0.0)
  ✅ Магазин (1.0.0)
  ...
✅ Загружено плагинов: 9
```

Откройте браузер: `http://localhost:8001/frontend/dashboard`

## 🎯 Как это работает

### Backend (Python)

1. При старте `discover_and_load_plugins()` сканирует `app/frontend/modules/`
2. Находит `plugin.py` в каждом модуле
3. Регистрирует плагин в `PluginRegistry`
4. Подключает роутер к FastAPI
5. Передает метаданные в шаблоны

### Frontend (JavaScript)

1. `dashboard.html` получает `window.__PLUGINS__` с метаданными
2. `app.js` создает `PluginManager`
3. `PluginManager` загружает JS модули плагинов
4. Каждый модуль становится доступен через `app.{module_name}`

### Sidebar

Собирается динамически из `sidebar_items` всех плагинов:

```python
sidebar_items = [
    {
        "id": "bots",
        "label": "dashboard.navigation.bots",
        "icon": "bi-people-fill",
        "url": "/frontend/bots/",
        "order": 10,
        "type": "htmx"
    }
]
```

## 📦 Структура плагина

```
app/frontend/modules/{module_name}/
├── __init__.py
├── plugin.py              # Описание плагина
├── router.py              # FastAPI роутер
├── static/
│   ├── js/
│   │   └── {module_name}.module.js  # JS модуль (опционально)
│   └── css/
│       └── {module_name}.css
└── templates/
    └── {module_name}.html
```

## 🔌 API плагина

### Python

```python
from app.frontend.core.plugin_system import Plugin


class MyPlugin(Plugin):
    name = "my_plugin"
    display_name = "Мой плагин"
    version = "1.0.0"
    
    static_css = ["my_plugin.css"]
    static_js = ["my_plugin.module.js"]
    
    sidebar_items = [{
        "label": "Мой плагин",
        "icon": "bi-star",
        "url": "/frontend/my_plugin/",
        "type": "htmx"
    }]
    
    def get_router(self):
        from .router import router
        return router
```

### JavaScript

```javascript
export default class MyPluginModule {
    constructor(app) {
        this.app = app;
        this.name = 'my_plugin';
    }
    
    async init() {
        console.log('✅ MyPlugin инициализирован');
        return this;
    }
    
    doSomething() {
        // Публичный API
    }
}
```

## 🎨 Использование

### В коде

```javascript
// Доступ к плагину
app.builder.openFlow('flow_id');
app.bots.openBotChat('bot_id', 'Bot Name');
app.store.installFlow('flow_id');

// Список загруженных плагинов
console.log(app.pluginManager.getLoadedNames());

// Hot reload для разработки
await app.pluginManager.reload('builder');
```

### В консоли браузера

```javascript
// Проверить метаданные
console.log(window.__PLUGINS__);

// Проверить загруженные плагины
console.log(app.pluginManager.getLoadedNames());

// Вызвать методы плагина
app.builder.saveCurrentFlow();
```

## 🌟 Преимущества

### ✅ Модульность
- Каждый плагин независим
- Можно включать/выключать
- Изоляция кода и стилей

### ✅ Расширяемость
- Sidebar формируется из плагинов
- Dashboard widgets
- Header actions
- Никаких изменений в `shared/`

### ✅ Единый API
```javascript
app.builder.{method}()
app.bots.{method}()
app.store.{method}()
```

### ✅ Lazy Loading
- JS модули загружаются только когда нужны
- CSS подключается динамически
- Быстрая начальная загрузка

### ✅ DX (Developer Experience)
- Добавить плагин = создать 1 файл `plugin.py`
- Автоматическая регистрация
- Hot reload для разработки
- Простое API

## 📚 Документация

Полная документация: [app/frontend/PLUGIN_SYSTEM.md](app/frontend/PLUGIN_SYSTEM.md)

## 🧪 Тестирование

1. Откройте `http://localhost:8001/frontend/dashboard`
2. Sidebar должен быть заполнен пунктами из плагинов
3. Откройте консоль браузера
4. Выполните:
   ```javascript
   console.log('Плагины:', app.pluginManager.getLoadedNames());
   console.log('Builder:', app.builder);
   console.log('Bots:', app.bots);
   ```

## 🔧 Отладка

### Плагин не загружается (Backend)

Проверьте логи при старте:
```
🔌 Загрузка плагинов фронтенда...
  ✅ Builder (1.0.0)
  ⏭️  landing - нет plugin.py (пропускаем)
```

### JS модуль не загружается (Frontend)

Откройте консоль:
```javascript
// Проверить метаданные
console.log(window.__PLUGINS__);

// Проверить ошибки загрузки
// Ищите "❌ Ошибка загрузки плагина"
```

## 📝 Следующие шаги

### Фаза 1 (текущая) ✅
- ✅ Ядро плагинной системы
- ✅ Автозагрузка плагинов
- ✅ Динамический sidebar
- ✅ 9 плагинов мигрировано

### Фаза 2 (опционально)
- [ ] Адаптировать существующий JS под плагинную систему
- [ ] Dashboard widgets
- [ ] Header actions
- [ ] Зависимости между плагинами

### Фаза 3 (будущее)
- [ ] Плагины в БД
- [ ] Marketplace плагинов
- [ ] Включение/выключение плагинов через UI
- [ ] Права доступа на уровне плагинов

## 🎊 Результат

**До:**
- 9 отдельных роутеров импортированы вручную в `main.py`
- Sidebar хардкоден в `dashboard.html`
- Изменения требуют правки `shared/`
- Нет единого API

**После:**
- Плагины загружаются автоматически
- Sidebar формируется динамически
- Каждый плагин изолирован
- Единый API: `app.{module}.{method}()`
- Добавить модуль = создать `plugin.py`

**Код стал проще, чище и модульнее! 🚀**

