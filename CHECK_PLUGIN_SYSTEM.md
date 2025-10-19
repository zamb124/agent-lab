# ✅ Чек-лист проверки плагинной системы

## 1️⃣ Перезапусти сервер

**ОБЯЗАТЕЛЬНО!** Плагины загружаются при старте.

```bash
# Останови старый процесс (Ctrl+C)
# Запусти заново:
uv run python run.py
```

**Ищи в логах:**
```
🔌 Загрузка плагинов фронтенда...
🔍 Поиск плагинов в modules/...
  ✅ Боты (1.0.0)
  ✅ Flow Builder (1.0.0)
  ✅ Магазин (1.0.0)
  ✅ История (1.0.0)
  ✅ Чаты (1.0.0)
  ✅ Переменные (1.0.0)
  ✅ Биллинг (1.0.0)
  ✅ Администрирование (1.0.0)
  ✅ Чат (1.0.0)
✅ Загружено плагинов: 9
```

Если не видишь эти логи - плагины не загрузились!

---

## 2️⃣ Открой браузер

```
http://localhost:8001/frontend/dashboard
```

**Hard reload:**
- Mac: `Cmd + Shift + R`
- Windows/Linux: `Ctrl + Shift + R`

---

## 3️⃣ Проверь консоль браузера (F12)

**Должны быть такие логи:**

```javascript
🔌 Инициализация плагинной системы...
🔍 Найдено плагинов: 3
📦 Загружаем плагин: builder
🎨 Инициализация Builder модуля
✅ Плагин builder загружен
📦 Загружаем плагин: bots
🤖 Инициализация Bots модуля
✅ Плагин bots загружен
📦 Загружаем плагин: store
🏪 Инициализация Store модуля
✅ Плагин store загружен
✅ Загружено плагинов: 3
```

Если не видишь - проблема с JS!

---

## 4️⃣ Выполни в консоли браузера

```javascript
// Проверь метаданные
console.log('Плагины:', window.__PLUGINS__);

// Проверь загруженные
console.log('Загружено:', app.pluginManager.getLoadedNames());

// Проверь app
console.log('Builder:', app.builder);
console.log('Bots:', app.bots);
console.log('Store:', app.store);
```

**Ожидаемый результат:**

```javascript
Плагины: Array(9) [{name: "builder", ...}, {name: "bots", ...}, ...]
Загружено: Array(3) ["builder", "bots", "store"]
Builder: BuilderModule {app: APP, name: "builder", ...}
Bots: BotsModule {app: APP, name: "bots", ...}
Store: StoreModule {app: APP, name: "store", ...}
```

---

## 5️⃣ Проверь sidebar

**До (статичный):**
```html[TODO: abilities.hero_description]
<!-- Хардкоден -->
<a href="/frontend/bots/">Боты</a>
<a href="/frontend/store/">Магазин</a>
```

**После (динамический):**
```html
<!-- Генерируется из плагинов -->
{% for item in sidebar_items %}
  <a href="{{ item.url }}">{{ t(item.label) }}</a>
{% endfor %}
```

Открой "View Page Source" (Ctrl+U) и найди sidebar - должны быть пункты из плагинов.

---

## 6️⃣ Что должно измениться визуально?

### **Sidebar:**
Порядок пунктов теперь по `order`:
1. Боты (order: 10)
2. Чаты (order: 20)
3. Магазин (order: 30)
4. История (order: 40)
5. Flow Builder (order: 50)
6. Ключи и Переменные (order: 60)

### **Функциональность:**
Вызовы через `app.{module}`:
```javascript
// Работает!
app.bots.openBotChat('bot_id', 'Bot Name');
app.builder.openFlow('flow_id');
app.store.installFlow('flow_id');
```

---

## 🔍 Отладка

### Плагины не загружаются (Backend)

**Проблема:** Нет логов `🔌 Загрузка плагинов`

**Решение:**
1. Проверь `app/main.py` строка ~176:
   ```python
   await discover_and_load_plugins(app)
   ```
2. Перезапусти сервер

---

### JS модули не загружаются (Frontend)

**Проблема:** В консоли ошибки загрузки

**Проверь:**
1. `window.__PLUGINS__` существует?
2. Файлы `.module.js` существуют в `static/{module}/js/`?
3. Есть ошибки в консоли?

**Типичные ошибки:**

```javascript
// ❌ Не экспортирует default
PluginClass is not a constructor

// ✅ Решение: добавь export default
export default class MyModule { ... }
```

---

## 📊 Сравнение

### **До:**

```python
# main.py - все роутеры вручную
from app.frontend.modules.bots.router import router as bots_module
from app.frontend.modules.store.router import router as store_module
...
app.include_router(bots_module)
app.include_router(store_module)
```

```html
<!-- dashboard.html - статичный sidebar -->
<a href="/frontend/bots/">Боты</a>
<a href="/frontend/store/">Магазин</a>
```

### **После:**

```python
# main.py - автозагрузка
await discover_and_load_plugins(app)
```

```html
<!-- dashboard.html - динамический -->
{% for item in sidebar_items %}
  <a href="{{ item.url }}">{{ t(item.label) }}</a>
{% endfor %}
```

```javascript
// app - единый API
app.bots.openBotChat()
app.builder.openFlow()
```

---

## ✅ Критерии успеха

- [ ] В логах сервера есть `✅ Загружено плагинов: 9`
- [ ] В консоли браузера есть `✅ Загружено плагинов: 3`
- [ ] `window.__PLUGINS__` содержит массив плагинов
- [ ] `app.builder`, `app.bots`, `app.store` существуют
- [ ] Sidebar отображается корректно
- [ ] Можно вызвать `app.bots.openBotChat()`

---

## 🆘 Если ничего не работает

1. **Перезапусти сервер**
2. **Hard reload страницы** (Cmd+Shift+R)
3. **Очисти кеш браузера**
4. **Проверь консоль на ошибки**
5. **Покажи логи сервера при старте**

---

## 💡 Быстрая проверка

**Открой консоль браузера и выполни:**

```javascript
// Одна команда для всех проверок
console.log({
  plugins: window.__PLUGINS__?.length,
  loaded: app.pluginManager?.getLoadedNames()?.length,
  builder: !!app.builder,
  bots: !!app.bots,
  store: !!app.store
});
```

**Ожидаемый результат:**
```javascript
{
  plugins: 9,
  loaded: 3,
  builder: true,
  bots: true,
  store: true
}
```

Если так - **система работает!** 🎉

